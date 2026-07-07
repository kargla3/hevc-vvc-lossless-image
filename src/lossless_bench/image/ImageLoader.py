"""Narzędzia do wczytywania obrazów."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError


class ImageLoader:
	"""Wczytuje obrazy z dysku i zamienia je na tablice NumPy."""

	kSupportedExtensions = {".png", ".bmp", ".tif", ".tiff", ".jpg", ".jpeg", ".webp"}

	def __init__(self, targetMode: str | None = None) -> None:
		"""Tworzy loader z opcjonalnym wymuszeniem trybu obrazu PIL."""

		self._targetMode = targetMode

	def loadImage(self, imagePath: str | Path) -> np.ndarray:
		"""Wczytuje pojedynczy obraz i zwraca go jako tablicę NumPy."""

		path = self._validatePath(imagePath)
		try:
			with Image.open(path) as image:
				preparedImage = self._prepareImage(image)
				return np.asarray(preparedImage)
		except UnidentifiedImageError as error:
			raise ValueError(f"Unsupported or corrupted image file: {path}") from error

	def loadImages(self, imagePaths: list[str | Path]) -> list[np.ndarray]:
		"""Wczytuje wiele obrazów zachowując kolejność wejściową."""

		if not imagePaths:
			return []

		return [self.loadImage(imagePath) for imagePath in imagePaths]

	def _validatePath(self, imagePath: str | Path) -> Path:
		"""Sprawdza, czy ścieżka wskazuje na istniejący plik graficzny."""

		path = Path(imagePath)
		if not path.exists():
			raise FileNotFoundError(f"Image file not found: {path}")
		if not path.is_file():
			raise IsADirectoryError(f"Expected a file, got a directory: {path}")
		if path.suffix.lower() not in self.kSupportedExtensions:
			raise ValueError(
				f"Unsupported image extension: {path.suffix}. "
				f"Supported extensions: {sorted(self.kSupportedExtensions)}"
			)
		return path

	def _prepareImage(self, image: Image.Image) -> Image.Image:
		"""Przygotowuje obraz do konwersji na tablicę NumPy."""

		if self._targetMode is not None and image.mode != self._targetMode:
			return image.convert(self._targetMode)
		return image
