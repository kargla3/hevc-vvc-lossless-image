"""Enkoder HEVC oparty o ffmpeg i libx265."""

from __future__ import annotations

from pathlib import Path

from ..config import EncodingMode
from .Encoder import Encoder, FrameInfo


kDefaultFfmpegPath = "ffmpeg"
kDefaultFrameRate = 30
kRawBitstreamSuffix = ".265"
kRawBitstreamSuffixes = {".265", ".hevc", ".h265"}
kDecodedFramePattern = "frame_%04d.png"
kInfiniteKeyframeInterval = "-1"

# Rozmiary CTU dopuszczane przez x265, od największego.
kCtuSizes = (64, 32, 16)


class HEVCEncoder(Encoder):
	"""Koduje sekwencje klatek bezstratnie kodekiem HEVC (libx265).

	Wejściem może być pojedynczy obraz (tryb FULL_IMAGE) albo katalog klatek PNG
	wyprodukowany przez ``VideoAssembler.framesToVideo()`` (tryby INTRA i INTER).
	Kodowanie jest zawsze bezstratne: ``lossless=1`` w połączeniu z formatem
	pikseli ``gbrp`` (RGB) albo ``gray`` (skala szarości) daje rekonstrukcję
	identyczną co do piksela.

	Tryb z konfiguracji steruje wyłącznie predykcją między klatkami:

	- FULL_IMAGE i INTRA — każda klatka kodowana niezależnie (``keyint=1``),
	- INTER — nieskończone GOP, tylko pierwsza klatka jest klatką kluczową.

	Rozmiar CTU jest dobierany automatycznie do rozmiaru klatki — powód opisuje
	``_ctuSizeFor()``. Można go nadpisać przez ``extra_params.x265_params.ctu``,
	ale przy małych kafelkach grozi to utratą bezstratności.
	"""

	kPixelFormatPerChannels = {1: "gray", 3: "gbrp"}

	def __init__(self, config, *, ffmpegPath: str | None = None) -> None:
		super().__init__(config)
		self._ffmpegPath = ffmpegPath or str(
			self.extraParams.get("ffmpeg_path", kDefaultFfmpegPath)
		)
		self._frameRate = int(self.extraParams.get("frame_rate", kDefaultFrameRate))

	def encode(self, src: str | Path, dst: str | Path) -> Path:
		"""Koduje obraz albo katalog klatek do bitstreamu HEVC."""

		source = self._normalizePath(src)
		frames = self._collectFrames(source)
		frameInfo = self._inspectFrames(frames)

		target = self._resolveBitstreamPath(dst)
		self._ensureParentDirectory(target)

		command = [self._ffmpegPath, "-y", "-loglevel", "error"]
		command += ["-framerate", str(self._frameRate)]
		command += self._buildInputArguments(source, frames)
		command += ["-an", "-c:v", "libx265"]
		command += ["-pix_fmt", self._pixelFormatFor(frameInfo)]
		command += ["-preset", self.preset]
		command += ["-x265-params", self._buildX265Params(frameInfo)]
		if target.suffix.lower() in kRawBitstreamSuffixes:
			command += ["-f", "hevc"]
		command += [str(target)]

		self._runTool(command, toolName=self._ffmpegPath, hint=self._ffmpegHint())
		return target

	def decode(self, src: str | Path, dst: str | Path) -> Path:
		"""Dekoduje bitstream HEVC do katalogu klatek PNG."""

		source = self._normalizePath(src)
		if not source.is_file():
			raise FileNotFoundError(f"HEVC bitstream not found: {source}")

		outputDirectory = self._normalizePath(dst)
		outputDirectory.mkdir(parents=True, exist_ok=True)

		command = [
			self._ffmpegPath,
			"-y",
			"-loglevel",
			"error",
			"-i",
			str(source),
			str(outputDirectory / kDecodedFramePattern),
		]
		self._runTool(command, toolName=self._ffmpegPath, hint=self._ffmpegHint())

		if not any(outputDirectory.glob("*.png")):
			raise RuntimeError(f"No frames were decoded from bitstream: {source}")

		return outputDirectory

	def getName(self) -> str:
		"""Zwraca nazwę enkodera używaną w raportach."""

		return "HEVC (libx265)"

	def _buildInputArguments(self, source: Path, frames: list[Path]) -> list[str]:
		"""Buduje argumenty wejściowe ffmpeg dla pliku albo katalogu klatek."""

		if source.is_file():
			return ["-i", str(source)]

		framePattern, startIndex = self._buildFramePattern(frames)
		return ["-start_number", str(startIndex), "-i", str(source / framePattern)]

	def _buildX265Params(self, frameInfo: FrameInfo) -> str:
		"""Buduje wartość opcji ``-x265-params`` dla trybu z konfiguracji."""

		params = ["lossless=1", "log-level=error"]
		if self.mode is EncodingMode.INTER:
			params.append(f"keyint={kInfiniteKeyframeInterval}")
		else:
			params.append("keyint=1")

		extraParams = dict(self.extraParams.get("x265_params", {}))
		if "ctu" not in extraParams:
			params.append(f"ctu={self._ctuSizeFor(frameInfo)}")

		for key, value in extraParams.items():
			params.append(f"{key}={value}")

		return ":".join(params)

	def _ctuSizeFor(self, frameInfo: FrameInfo) -> int:
		"""Dobiera rozmiar CTU mieszczący się w klatce więcej niż raz.

		x265 3.5 gubi bezstratność w trybie międzyklatkowym, gdy cała klatka
		mieści się w jednym CTU (np. kafelek 64x64 przy domyślnym ``ctu=64``):
		zdekodowany obraz różni się wtedy od źródła o kilkadziesiąt poziomów,
		mimo że enkoder raportuje ``Rate Control: Lossless``. Kafelki bywają
		małe, więc CTU jest dobierane tak, by było mniejsze od obu wymiarów
		klatki. Przy dużych klatkach nic to nie zmienia — zostaje ``ctu=64``.
		"""

		smallerSide = min(frameInfo.width, frameInfo.height)
		for ctuSize in kCtuSizes:
			if ctuSize < smallerSide:
				return ctuSize

		return kCtuSizes[-1]

	def _pixelFormatFor(self, frameInfo: FrameInfo) -> str:
		"""Dobiera format pikseli zachowujący bezstratność dla danych wejściowych."""

		pixelFormat = self.kPixelFormatPerChannels.get(frameInfo.channels)
		if pixelFormat is None:
			raise ValueError(
				f"Unsupported number of channels for lossless HEVC: {frameInfo.channels}"
			)
		return pixelFormat

	def _resolveBitstreamPath(self, dst: str | Path) -> Path:
		"""Uzupełnia domyślne rozszerzenie bitstreamu, jeśli go brakuje."""

		target = self._normalizePath(dst)
		if target.is_dir():
			raise IsADirectoryError(
				f"HEVC output must be a file, got a directory: {target}"
			)
		if target.suffix == "":
			return target.with_suffix(kRawBitstreamSuffix)
		return target

	def _ffmpegHint(self) -> str:
		"""Zwraca podpowiedź dołączaną do komunikatu o brakującym ffmpeg."""

		return (
			"Install ffmpeg with libx265 support or set extra_params.ffmpeg_path "
			"to its location."
		)


__all__ = ["HEVCEncoder"]
