"""Encoder abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Callable, Sequence

import numpy as np
from PIL import Image

from ..config import EncoderConfig
from ..image.ImageLoader import ImageLoader
from ..image.ImageSaver import ImageSaver


kFrameExtension = ".png"
kFramePattern = re.compile(r"^(?P<prefix>.*?)(?P<index>\d+)(?P<suffix>\.[^.]+)$")


@dataclass(frozen=True)
class FrameInfo:
	"""Podstawowe właściwości sekwencji klatek przekazywanej do enkodera."""

	width: int
	height: int
	channels: int
	count: int


class Encoder(ABC):
	"""Bazowa klasa dla wszystkich enkoderów używanych w benchmarku."""

	kChannelsPerMode = {"L": 1, "RGB": 3}

	def __init__(self, config: EncoderConfig) -> None:
		if not isinstance(config, EncoderConfig):
			raise TypeError("config must be an EncoderConfig instance")
		self._config = config

	@property
	def config(self) -> EncoderConfig:
		"""Zwraca konfigurację enkodera."""

		return self._config

	@property
	def codec(self) -> str:
		"""Zwraca nazwę kodeka z konfiguracji."""

		return self._config.codec

	@property
	def mode(self):
		"""Zwraca tryb pracy enkodera."""

		return self._config.mode

	@property
	def preset(self) -> str:
		"""Zwraca preset enkodera."""

		return self._config.preset

	@property
	def extraParams(self) -> dict:
		"""Zwraca dodatkowe parametry enkodera."""

		return self._config.extra_params

	@abstractmethod
	def encode(self, src: str | Path, dst: str | Path) -> Path:
		"""Koduje wejście do docelowego pliku."""

	@abstractmethod
	def decode(self, src: str | Path, dst: str | Path) -> Path:
		"""Dekoduje wejście do docelowego pliku."""

	@abstractmethod
	def getName(self) -> str:
		"""Zwraca nazwę enkodera używaną w raportach."""

	def _normalizePath(self, path: str | Path) -> Path:
		"""Normalizuje ścieżkę wejściową bez sprawdzania istnienia."""

		return Path(path).expanduser()

	def _ensureParentDirectory(self, path: Path) -> Path:
		"""Tworzy katalog nadrzędny dla ścieżki wyjściowej."""

		path.parent.mkdir(parents=True, exist_ok=True)
		return path

	def _collectFrames(self, source: Path) -> list[Path]:
		"""Zwraca uporządkowaną listę klatek dla pojedynczego pliku albo katalogu."""

		if not source.exists():
			raise FileNotFoundError(f"Encoder source not found: {source}")

		if source.is_file():
			return [source]

		framePaths = sorted(source.glob(f"*{kFrameExtension}"))
		if not framePaths:
			raise ValueError(f"No {kFrameExtension} frames found in directory: {source}")
		return framePaths

	def _buildFramePattern(self, frames: Sequence[Path]) -> tuple[str, int]:
		"""Zwraca wzorzec nazw w stylu printf oraz numer pierwszej klatki.

		Wzorzec jest wykrywany z nazw plików (np. ``frame_0000.png`` daje
		``frame_%04d.png``) i nadaje się do przekazania jako wejście dla ffmpeg.
		"""

		if not frames:
			raise ValueError("frames must not be empty")

		matches = [kFramePattern.match(path.name) for path in frames]
		if any(match is None for match in matches):
			raise ValueError(
				"Frame file names must end with a number, for example frame_0000.png"
			)

		prefix = matches[0].group("prefix")
		suffix = matches[0].group("suffix")
		indexWidth = len(matches[0].group("index"))
		startIndex = int(matches[0].group("index"))

		for offset, match in enumerate(matches):
			if match.group("prefix") != prefix or match.group("suffix") != suffix:
				raise ValueError(
					"All frames must share the same name prefix and extension: "
					f"{frames[offset].name} does not match {frames[0].name}"
				)
			if len(match.group("index")) != indexWidth:
				raise ValueError(
					"All frames must use the same number of digits: "
					f"{frames[offset].name} does not match {frames[0].name}"
				)
			if int(match.group("index")) != startIndex + offset:
				raise ValueError(
					"Frames must be numbered consecutively, missing index "
					f"{startIndex + offset} before {frames[offset].name}"
				)

		return f"{prefix}%0{indexWidth}d{suffix}", startIndex

	def _inspectFrames(self, frames: Sequence[Path]) -> FrameInfo:
		"""Odczytuje wymiary i liczbę kanałów na podstawie pierwszej klatki."""

		if not frames:
			raise ValueError("frames must not be empty")

		with Image.open(frames[0]) as image:
			mode = image.mode
			width, height = image.size

		if mode not in self.kChannelsPerMode:
			raise ValueError(
				f"Unsupported image mode '{mode}' in {frames[0]}. "
				f"Supported modes: {sorted(self.kChannelsPerMode)}. "
				"Convert the image with ImageLoader(targetMode=...) first."
			)

		return FrameInfo(
			width=width,
			height=height,
			channels=self.kChannelsPerMode[mode],
			count=len(frames),
		)

	def _encodeFrameFiles(
		self,
		source: Path,
		frames: Sequence[Path],
		dst: str | Path,
		*,
		suffix: str,
		encodeFrame: Callable[[np.ndarray], bytes],
	) -> Path:
		"""Koduje każdą klatkę do osobnego bitstreamu.

		Pojedynczy obraz na wejściu daje pojedynczy plik, a katalog klatek daje
		katalog bitstreamów o nazwach ``frame_0000<suffix>``.
		"""

		imageLoader = ImageLoader()

		if source.is_file():
			target = self._normalizePath(dst)
			if target.suffix == "":
				target = target.with_suffix(suffix)
			self._ensureParentDirectory(target)
			target.write_bytes(encodeFrame(imageLoader.loadImage(frames[0])))
			return target

		outputDirectory = self._normalizePath(dst)
		if outputDirectory.exists() and not outputDirectory.is_dir():
			raise NotADirectoryError(
				f"Expected a directory, got a file: {outputDirectory}"
			)

		outputDirectory.mkdir(parents=True, exist_ok=True)
		for stalePath in outputDirectory.glob(f"*{suffix}"):
			stalePath.unlink()

		for index, framePath in enumerate(frames):
			bitstreamPath = outputDirectory / f"frame_{index:04d}{suffix}"
			bitstreamPath.write_bytes(encodeFrame(imageLoader.loadImage(framePath)))

		return outputDirectory

	def _decodeFrameFiles(
		self,
		source: Path,
		dst: str | Path,
		*,
		suffix: str,
		decodeFrame: Callable[[bytes], np.ndarray],
	) -> Path:
		"""Dekoduje bitstream albo katalog bitstreamów do katalogu klatek PNG."""

		if not source.exists():
			raise FileNotFoundError(f"Encoder source not found: {source}")

		if source.is_file():
			bitstreamPaths = [source]
		else:
			bitstreamPaths = sorted(source.glob(f"*{suffix}"))
			if not bitstreamPaths:
				raise ValueError(f"No {suffix} bitstreams found in directory: {source}")

		outputDirectory = self._normalizePath(dst)
		outputDirectory.mkdir(parents=True, exist_ok=True)

		imageSaver = ImageSaver()
		for index, bitstreamPath in enumerate(bitstreamPaths):
			frame = decodeFrame(bitstreamPath.read_bytes())
			imageSaver.saveImage(frame, outputDirectory / f"frame_{index:04d}{kFrameExtension}")

		return outputDirectory

	def _runCommand(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
		"""Uruchamia komendę i podnosi czytelny wyjątek przy błędzie."""

		try:
			return subprocess.run(
				list(command),
				check=True,
				capture_output=True,
				text=True,
			)
		except FileNotFoundError as error:
			raise FileNotFoundError(
				"Required external command was not found in PATH."
			) from error
		except subprocess.CalledProcessError as error:
			stderr = error.stderr.strip() if error.stderr else ""
			raise RuntimeError(
				f"Encoder command failed with exit code {error.returncode}: {stderr}"
			) from error

	def _runTool(
		self,
		command: Sequence[str],
		*,
		toolName: str | None = None,
		hint: str = "",
	) -> subprocess.CompletedProcess[str]:
		"""Uruchamia narzędzie zewnętrzne i nazywa je w komunikacie o braku pliku."""

		name = toolName or (command[0] if command else "external command")
		try:
			return self._runCommand(command)
		except FileNotFoundError as error:
			message = f"'{name}' was not found in PATH."
			raise FileNotFoundError(f"{message} {hint}".strip()) from error


__all__ = ["Encoder", "FrameInfo"]
