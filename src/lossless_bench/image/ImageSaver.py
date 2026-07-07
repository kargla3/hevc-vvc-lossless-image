"""Narzędzia do zapisywania obrazów."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


class ImageSaver:
	"""Zapisuje obrazy z tablic NumPy lub obiektów PIL do plików."""

	kDefaultFormat = "PNG"

	def saveImage(
		self,
		image: np.ndarray | Image.Image,
		outputPath: str | Path,
		*,
		formatName: str | None = None,
		compressLevel: int | None = None,
	) -> Path:
		"""Zapisuje pojedynczy obraz do pliku i zwraca docelową ścieżkę."""

		path = self._prepareOutputPath(outputPath, formatName=formatName)
		pilImage = self._toPillowImage(image)

		saveKwargs: dict[str, object] = {}
		if formatName is not None:
			saveKwargs["format"] = formatName
		if compressLevel is not None:
			saveKwargs["compress_level"] = compressLevel

		pilImage.save(path, **saveKwargs)
		return path

	def saveImages(
		self,
		images: list[np.ndarray | Image.Image],
		outputDir: str | Path,
		*,
		baseName: str = "frame",
		startIndex: int = 0,
		formatName: str | None = None,
	) -> list[Path]:
		"""Zapisuje wiele obrazów do katalogu z kolejnymi nazwami plików."""

		if not images:
			return []

		outputDirectory = self._prepareOutputDirectory(outputDir)
		writtenPaths: list[Path] = []
		fileFormat = formatName or self.kDefaultFormat
		fileExtension = self._extensionForFormat(fileFormat)

		for index, image in enumerate(images, start=startIndex):
			filePath = outputDirectory / f"{baseName}_{index:04d}{fileExtension}"
			writtenPaths.append(self.saveImage(image, filePath, formatName=fileFormat))

		return writtenPaths

	def _prepareOutputPath(self, outputPath: str | Path, *, formatName: str | None = None) -> Path:
		"""Przygotowuje ścieżkę pliku i tworzy katalog nadrzędny."""

		path = Path(outputPath)
		if path.suffix == "" and formatName is not None:
			path = path.with_suffix(self._extensionForFormat(formatName))
		elif path.suffix == "":
			path = path.with_suffix(f".{self.kDefaultFormat.lower()}")
		path.parent.mkdir(parents=True, exist_ok=True)
		return path

	def _prepareOutputDirectory(self, outputDir: str | Path) -> Path:
		"""Przygotowuje katalog wyjściowy."""

		path = Path(outputDir)
		path.mkdir(parents=True, exist_ok=True)
		return path

	def _toPillowImage(self, image: np.ndarray | Image.Image) -> Image.Image:
		"""Konwertuje wejście do obiektu PIL Image."""

		if isinstance(image, Image.Image):
			return image
		if not isinstance(image, np.ndarray):
			raise TypeError("image must be a numpy.ndarray or PIL.Image.Image")
		if image.ndim not in (2, 3):
			raise ValueError("image must be 2D (H,W) or 3D (H,W,C)")
		return Image.fromarray(image)

	@staticmethod
	def _extensionForFormat(formatName: str) -> str:
		"""Zwraca domyślne rozszerzenie dla wskazanego formatu."""

		normalizedFormat = formatName.upper()
		if normalizedFormat == "PNG":
			return ".png"
		if normalizedFormat in {"TIFF", "TIF"}:
			return ".tiff"
		if normalizedFormat in {"JPG", "JPEG"}:
			return ".jpg"
		if normalizedFormat == "WEBP":
			return ".webp"
		return f".{normalizedFormat.lower()}"
