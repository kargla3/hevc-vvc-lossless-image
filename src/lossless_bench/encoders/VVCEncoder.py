"""Enkoder VVC oparty o vvencapp i vvdecapp."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..config import EncodingMode
from .Encoder import Encoder, FrameInfo


kDefaultFfmpegPath = "ffmpeg"
kDefaultEncoderPath = "vvencapp"
kDefaultDecoderPath = "vvdecapp"
kEncoderPathVariable = "VVENC_PATH"
kDecoderPathVariable = "VVDEC_PATH"

kDefaultFrameRate = 30
kDefaultQp = 0
kInternalBitDepth = "8"
kInterRefreshSeconds = "1000"

kGrayPlanesFormat = "gray_planes"
kYuv420Format = "yuv420"
kColorPlanes = ("g", "b", "r")
kLumaPlane = "y"

kManifestName = "meta.json"
kBitstreamSuffix = ".266"
kSingleStreamName = f"stream{kBitstreamSuffix}"
kDecodedFramePattern = "frame_%04d.png"


class VVCEncoder(Encoder):
	"""Koduje sekwencje klatek kodekiem VVC (vvencapp) z QP 0.

	Uwaga na dwa ograniczenia narzędzia, które wpływają na interpretację wyników:

	1. VVenC **nie ma trybu prawdziwie bezstratnego** (brak TransquantBypass).
	   Kodowanie z QP 0 jest jedynie przybliżeniem bezstratności: na gładkich
	   obszarach rekonstrukcja bywa dokładna, ale na treści szumowej część
	   pikseli różni się o ±1. Wyniki VVC należy raportować jako *near-lossless*.
	2. VVenC przyjmuje wyłącznie yuv400 (skala szarości) i yuv420 — nie obsługuje
	   4:4:4, więc obrazu RGB nie da się podać wprost bez straty na chromie.

	Stąd dwie ścieżki wybierane przez ``extra_params.input_format``:

	- ``gray_planes`` (domyślna) — obraz RGB rozbijany na trzy niezależne
	  strumienie yuv400, jeden na składową. Nie ma straty na podpróbkowaniu
	  chromy, kosztem trzykrotnego kodowania.
	- ``yuv420`` — jeden strumień, ale RGB traci chrominancję przez
	  podpróbkowanie. Przydatne do zmierzenia, ile to podpróbkowanie kosztuje.

	Wynikiem ``encode()`` jest **katalog** zawierający bitstreamy ``.266`` oraz
	manifest ``meta.json`` z wymiarami i układem płaszczyzn. Manifest jest
	konieczny, bo ``vvdecapp`` zapisuje surowy YUV bez nagłówka; jego rozmiar
	(rzędu 100 bajtów) nie jest częścią bitstreamu i nie powinien być wliczany
	do metryk kompresji.
	"""

	kSupportedInputFormats = (kGrayPlanesFormat, kYuv420Format)

	def __init__(
		self,
		config,
		*,
		ffmpegPath: str | None = None,
		encoderPath: str | None = None,
		decoderPath: str | None = None,
	) -> None:
		super().__init__(config)
		self._ffmpegPath = ffmpegPath or str(
			self.extraParams.get("ffmpeg_path", kDefaultFfmpegPath)
		)
		self._encoderPath = encoderPath or self._resolveToolPath(
			"vvenc_path", kEncoderPathVariable, kDefaultEncoderPath
		)
		self._decoderPath = decoderPath or self._resolveToolPath(
			"vvdec_path", kDecoderPathVariable, kDefaultDecoderPath
		)
		self._frameRate = int(self.extraParams.get("frame_rate", kDefaultFrameRate))
		self._qp = int(self.extraParams.get("qp", kDefaultQp))
		self._inputFormat = str(self.extraParams.get("input_format", kGrayPlanesFormat))

		if self._inputFormat not in self.kSupportedInputFormats:
			raise ValueError(
				f"Unsupported input_format '{self._inputFormat}'. "
				f"Supported values: {list(self.kSupportedInputFormats)}"
			)

	def encode(self, src: str | Path, dst: str | Path) -> Path:
		"""Koduje obraz albo katalog klatek do katalogu bitstreamów VVC."""

		source = self._normalizePath(src)
		frames = self._collectFrames(source)
		frameInfo = self._inspectFrames(frames)

		outputDirectory = self._prepareOutputDirectory(dst)
		planeNames = self._planeNamesFor(frameInfo)

		with tempfile.TemporaryDirectory(prefix="vvc_encode_") as tempDir:
			rawDirectory = Path(tempDir)
			for planeName in planeNames:
				rawPath = rawDirectory / f"{planeName}.yuv"
				self._extractRawPlane(source, frames, planeName, rawPath)
				self._encodePlane(
					rawPath,
					outputDirectory / self._bitstreamNameFor(planeName),
					frameInfo,
				)

		self._writeManifest(outputDirectory, frameInfo, planeNames)
		return outputDirectory

	def decode(self, src: str | Path, dst: str | Path) -> Path:
		"""Dekoduje katalog bitstreamów VVC do katalogu klatek PNG."""

		source = self._normalizePath(src)
		manifest = self._readManifest(source)

		outputDirectory = self._normalizePath(dst)
		outputDirectory.mkdir(parents=True, exist_ok=True)

		planeNames = list(manifest["planes"])
		width = int(manifest["width"])
		height = int(manifest["height"])

		with tempfile.TemporaryDirectory(prefix="vvc_decode_") as tempDir:
			rawDirectory = Path(tempDir)
			rawPaths: list[Path] = []
			for planeName in planeNames:
				rawPath = rawDirectory / f"{planeName}.yuv"
				self._decodePlane(source / self._bitstreamNameFor(planeName), rawPath)
				self._validateRawSize(rawPath, width, height, manifest)
				rawPaths.append(rawPath)

			self._assembleFrames(rawPaths, manifest, outputDirectory)

		if not any(outputDirectory.glob("*.png")):
			raise RuntimeError(f"No frames were decoded from bitstreams in: {source}")

		return outputDirectory

	def getName(self) -> str:
		"""Zwraca nazwę enkodera używaną w raportach."""

		return f"VVC (vvenc, {self._inputFormat}, qp={self._qp})"

	def _extractRawPlane(
		self,
		source: Path,
		frames: list[Path],
		planeName: str,
		rawPath: Path,
	) -> None:
		"""Zapisuje wskazaną płaszczyznę wejścia jako surowy plik YUV."""

		command = [self._ffmpegPath, "-y", "-loglevel", "error"]
		command += ["-framerate", str(self._frameRate)]
		command += self._buildInputArguments(source, frames)
		command += self._buildPlaneFilterArguments(planeName)
		command += ["-f", "rawvideo", str(rawPath)]
		self._runTool(command, toolName=self._ffmpegPath, hint=self._ffmpegHint())

	def _buildPlaneFilterArguments(self, planeName: str) -> list[str]:
		"""Buduje argumenty ffmpeg wybierające jedną płaszczyznę wejścia."""

		if planeName == kYuv420Format:
			return ["-pix_fmt", "yuv420p"]
		if planeName == kLumaPlane:
			return ["-pix_fmt", "gray"]
		return ["-vf", f"format=gbrp,extractplanes={planeName}", "-pix_fmt", "gray"]

	def _encodePlane(self, rawPath: Path, bitstreamPath: Path, frameInfo: FrameInfo) -> None:
		"""Koduje pojedynczy surowy strumień YUV do bitstreamu VVC."""

		command = [
			self._encoderPath,
			"-i",
			str(rawPath),
			"-o",
			str(bitstreamPath),
			"--size",
			f"{frameInfo.width}x{frameInfo.height}",
			"--format",
			self._vvencInputFormat(),
			"--framerate",
			str(self._frameRate),
			"--preset",
			self.preset,
			"--qp",
			str(self._qp),
			"--qpa",
			"0",
			"--internal-bitdepth",
			kInternalBitDepth,
			"--verbosity",
			"1",
		]
		command += self._buildIntraArguments()
		self._runTool(command, toolName=self._encoderPath, hint=self._vvencHint())

	def _decodePlane(self, bitstreamPath: Path, rawPath: Path) -> None:
		"""Dekoduje pojedynczy bitstream VVC do surowego pliku YUV."""

		if not bitstreamPath.is_file():
			raise FileNotFoundError(f"VVC bitstream not found: {bitstreamPath}")

		command = [
			self._decoderPath,
			"-b",
			str(bitstreamPath),
			"-o",
			str(rawPath),
			"-v",
			"1",
		]
		self._runTool(command, toolName=self._decoderPath, hint=self._vvdecHint())

	def _assembleFrames(
		self,
		rawPaths: list[Path],
		manifest: dict,
		outputDirectory: Path,
	) -> None:
		"""Składa surowe płaszczyzny z powrotem w klatki PNG."""

		width = int(manifest["width"])
		height = int(manifest["height"])
		inputFormat = str(manifest["format"])

		command = [self._ffmpegPath, "-y", "-loglevel", "error"]
		pixelFormat = "yuv420p" if inputFormat == kYuv420Format else "gray"
		for rawPath in rawPaths:
			command += [
				"-f",
				"rawvideo",
				"-pix_fmt",
				pixelFormat,
				"-s",
				f"{width}x{height}",
				"-framerate",
				str(self._frameRate),
				"-i",
				str(rawPath),
			]

		if inputFormat == kYuv420Format:
			command += ["-pix_fmt", "rgb24"]
		elif len(rawPaths) == len(kColorPlanes):
			# Płaszczyzny wracają w kolejności g, b, r, czyli w kolejności planów gbrp.
			command += [
				"-filter_complex",
				"[0:v][1:v][2:v]mergeplanes=0x001020:gbrp[out]",
				"-map",
				"[out]",
				"-pix_fmt",
				"rgb24",
			]
		else:
			command += ["-pix_fmt", "gray"]

		command += [str(outputDirectory / kDecodedFramePattern)]
		self._runTool(command, toolName=self._ffmpegPath, hint=self._ffmpegHint())

	def _buildInputArguments(self, source: Path, frames: list[Path]) -> list[str]:
		"""Buduje argumenty wejściowe ffmpeg dla pliku albo katalogu klatek."""

		if source.is_file():
			return ["-i", str(source)]

		framePattern, startIndex = self._buildFramePattern(frames)
		return ["-start_number", str(startIndex), "-i", str(source / framePattern)]

	def _buildIntraArguments(self) -> list[str]:
		"""Dobiera okres klatek kluczowych do trybu z konfiguracji."""

		if self.mode is EncodingMode.INTER:
			return ["--refreshsec", kInterRefreshSeconds]
		return ["--intraperiod", "1"]

	def _planeNamesFor(self, frameInfo: FrameInfo) -> list[str]:
		"""Zwraca listę płaszczyzn kodowanych osobno dla danego wejścia."""

		if self._inputFormat == kYuv420Format:
			return [kYuv420Format]
		if frameInfo.channels == 1:
			return [kLumaPlane]
		return list(kColorPlanes)

	def _vvencInputFormat(self) -> str:
		"""Zwraca nazwę formatu wejściowego oczekiwaną przez vvencapp."""

		return "yuv420" if self._inputFormat == kYuv420Format else "yuv400"

	def _bitstreamNameFor(self, planeName: str) -> str:
		"""Zwraca nazwę pliku bitstreamu dla wskazanej płaszczyzny."""

		if planeName == kYuv420Format:
			return kSingleStreamName
		return f"plane_{planeName}{kBitstreamSuffix}"

	def _prepareOutputDirectory(self, dst: str | Path) -> Path:
		"""Tworzy katalog wyjściowy i usuwa pozostałości po poprzednim kodowaniu."""

		outputDirectory = self._normalizePath(dst)
		if outputDirectory.exists() and not outputDirectory.is_dir():
			raise NotADirectoryError(
				f"VVC output must be a directory, got a file: {outputDirectory}"
			)

		outputDirectory.mkdir(parents=True, exist_ok=True)
		for staleName in (
			*(f"plane_{plane}{kBitstreamSuffix}" for plane in (*kColorPlanes, kLumaPlane)),
			kSingleStreamName,
			kManifestName,
		):
			(outputDirectory / staleName).unlink(missing_ok=True)

		return outputDirectory

	def _writeManifest(
		self,
		outputDirectory: Path,
		frameInfo: FrameInfo,
		planeNames: list[str],
	) -> None:
		"""Zapisuje dane potrzebne dekoderowi do odtworzenia klatek."""

		manifest = {
			"format": self._inputFormat,
			"planes": planeNames,
			"width": frameInfo.width,
			"height": frameInfo.height,
			"frame_count": frameInfo.count,
			"channels": frameInfo.channels,
			"bit_depth": int(kInternalBitDepth),
			"qp": self._qp,
			"preset": self.preset,
			"mode": self.mode.value,
		}
		manifestPath = outputDirectory / kManifestName
		manifestPath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

	def _readManifest(self, source: Path) -> dict:
		"""Wczytuje manifest zapisany podczas kodowania."""

		if not source.is_dir():
			raise NotADirectoryError(
				f"VVC decoding expects the directory produced by encode(), got: {source}"
			)

		manifestPath = source / kManifestName
		if not manifestPath.is_file():
			raise FileNotFoundError(f"VVC manifest not found: {manifestPath}")

		manifest = json.loads(manifestPath.read_text(encoding="utf-8"))
		if not isinstance(manifest, dict) or "planes" not in manifest:
			raise ValueError(f"Invalid VVC manifest: {manifestPath}")

		return manifest

	def _validateRawSize(
		self,
		rawPath: Path,
		width: int,
		height: int,
		manifest: dict,
	) -> None:
		"""Sprawdza, czy dekoder zwrócił 8-bitowe dane o oczekiwanym rozmiarze."""

		samplesPerFrame = width * height
		if str(manifest["format"]) == kYuv420Format:
			samplesPerFrame = samplesPerFrame * 3 // 2

		expectedBytes = samplesPerFrame * int(manifest["frame_count"])
		actualBytes = rawPath.stat().st_size
		if actualBytes == expectedBytes:
			return

		raise RuntimeError(
			f"Unexpected decoded size for {rawPath.name}: got {actualBytes} bytes, "
			f"expected {expectedBytes}. The bitstream was probably not encoded with "
			f"--internal-bitdepth {kInternalBitDepth}."
		)

	def _resolveToolPath(self, paramName: str, variableName: str, defaultPath: str) -> str:
		"""Ustala ścieżkę narzędzia: konfiguracja, zmienna środowiskowa, PATH."""

		configuredPath = self.extraParams.get(paramName)
		if configuredPath:
			return str(configuredPath)
		return os.environ.get(variableName) or defaultPath

	def _ffmpegHint(self) -> str:
		"""Zwraca podpowiedź dołączaną do komunikatu o brakującym ffmpeg."""

		return "Install ffmpeg or set extra_params.ffmpeg_path to its location."

	def _vvencHint(self) -> str:
		"""Zwraca podpowiedź dołączaną do komunikatu o brakującym vvencapp."""

		return (
			"Build VVenC or set extra_params.vvenc_path (or the "
			f"{kEncoderPathVariable} environment variable) to the vvencapp binary."
		)

	def _vvdecHint(self) -> str:
		"""Zwraca podpowiedź dołączaną do komunikatu o brakującym vvdecapp."""

		return (
			"Build VVdeC or set extra_params.vvdec_path (or the "
			f"{kDecoderPathVariable} environment variable) to the vvdecapp binary."
		)


__all__ = ["VVCEncoder"]
