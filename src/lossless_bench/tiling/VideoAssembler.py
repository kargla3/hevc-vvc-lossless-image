"""Tile/frame assembler utilities."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from ..image.ImageLoader import ImageLoader
from ..image.ImageSaver import ImageSaver
from .Tiler import Tile


class VideoAssembler:
	"""Buduje uporządkowane sekwencje klatek PNG i odczytuje je z wideo."""

	kDefaultFrameFormat = "PNG"
	kDefaultFramePattern = "frame_%04d.png"

	def __init__(self, *, ffmpegPath: str = "ffmpeg") -> None:
		self._ffmpegPath = ffmpegPath
		self._imageSaver = ImageSaver()
		self._imageLoader = ImageLoader()

	def framesToVideo(
		self,
		frames: Sequence[np.ndarray | Image.Image | Tile],
		outputPath: str | Path,
		*,
		baseName: str = "frame",
		startIndex: int = 0,
		formatName: str = kDefaultFrameFormat,
	) -> Path:
		"""Zapisuje sekwencję klatek jako uporządkowany katalog PNG."""

		if not frames:
			raise ValueError("frames must not be empty")

		outputDirectory = Path(outputPath)
		if outputDirectory.exists() and not outputDirectory.is_dir():
			raise NotADirectoryError(f"Expected a directory, got a file: {outputDirectory}")

		outputDirectory.mkdir(parents=True, exist_ok=True)
		normalizedFrames = [self._normalizeFrame(frame) for frame in frames]
		self._imageSaver.saveImages(
			normalizedFrames,
			outputDirectory,
			baseName=baseName,
			startIndex=startIndex,
			formatName=formatName,
		)
		return outputDirectory

	def videoToFrames(
		self,
		sourcePath: str | Path,
		*,
		outputDir: str | Path | None = None,
		framePattern: str = kDefaultFramePattern,
	) -> list[np.ndarray]:
		"""Wczytuje klatki z katalogu PNG albo wypakowuje je z pliku wideo."""

		source = Path(sourcePath)
		if not source.exists():
			raise FileNotFoundError(f"Source path not found: {source}")

		if source.is_dir():
			framePaths = sorted(source.glob("*.png"))
			if not framePaths:
				raise ValueError(f"No PNG frames found in directory: {source}")
			return self._imageLoader.loadImages(framePaths)

		if outputDir is None:
			with tempfile.TemporaryDirectory(prefix="video_assembler_frames_") as tempDir:
				return self._extractFrames(source, Path(tempDir), framePattern=framePattern)

		return self._extractFrames(source, Path(outputDir), framePattern=framePattern)

	def _extractFrames(
		self,
		videoPath: Path,
		outputDir: Path,
		*,
		framePattern: str,
	) -> list[np.ndarray]:
		"""Wypakowuje klatki z pliku wideo do katalogu tymczasowego."""

		outputDir.mkdir(parents=True, exist_ok=True)
		outputPattern = outputDir / framePattern
		command = [
			self._ffmpegPath,
			"-y",
			"-i",
			str(videoPath),
			str(outputPattern),
		]
		self._runFfmpeg(command)

		framePaths = sorted(outputDir.glob("*.png"))
		if not framePaths:
			raise ValueError(f"No frames were extracted from video: {videoPath}")

		return self._imageLoader.loadImages(framePaths)

	def _normalizeFrame(self, frame: np.ndarray | Image.Image | Tile) -> np.ndarray | Image.Image:
		"""Zamienia kafelek na jego dane albo przepuszcza obraz bez zmian."""

		if isinstance(frame, Tile):
			return frame.data
		if isinstance(frame, (np.ndarray, Image.Image)):
			return frame
		raise TypeError("frames must contain numpy arrays, PIL images, or Tile objects")

	def _runFfmpeg(self, command: list[str]) -> None:
		"""Uruchamia ffmpeg i podnosi czytelny błąd przy niepowodzeniu."""

		try:
			subprocess.run(command, check=True, capture_output=True, text=True)
		except FileNotFoundError as error:
			raise FileNotFoundError(
				f"ffmpeg not found at '{self._ffmpegPath}'. Ensure it is available in PATH."
			) from error
		except subprocess.CalledProcessError as error:
			raise RuntimeError(
				"ffmpeg failed while processing frames: "
				f"{error.stderr.strip() if error.stderr else error}"
			) from error
