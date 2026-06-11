"""Abstrakcja tilera.

Moduł definiuje wspólny interfejs i narzędzia pomocnicze dla konkretnych
strategii kafelkowania (np. raster, Hilbert, Z-order).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import ceil

import numpy as np


@dataclass(frozen=True)
class Tile:
	"""Pojedynczy kafelek obrazu wraz z pozycją w siatce."""

	row: int
	col: int
	data: np.ndarray


class Tiler(ABC):
	"""Klasa bazowa dla tilerów obrazu.

	Implementacje pochodne definiują porządek przechodzenia po kafelkach,
	a ta klasa dostarcza wspólną walidację i operacje geometryczne.
	"""

	def __init__(self, tileHeight: int, tileWidth: int) -> None:
		self._validateTileSize(tileHeight=tileHeight, tileWidth=tileWidth)
		self._tileHeight = tileHeight
		self._tileWidth = tileWidth

	@abstractmethod
	def splitTiles(self, image: np.ndarray) -> list[Tile]:
		"""Dzieli tablicę obrazu na uporządkowane kafelki."""

	@abstractmethod
	def mergeTiles(self, tiles: list[Tile], outputShape: tuple[int, ...]) -> np.ndarray:
		"""Scala uporządkowane kafelki z powrotem do tablicy obrazu."""

	@property
	def tileHeight(self) -> int:
		"""Wysokość kafelka w pikselach."""

		return self._tileHeight

	@property
	def tileWidth(self) -> int:
		"""Szerokość kafelka w pikselach."""

		return self._tileWidth

	@staticmethod
	def _validateImage(image: np.ndarray) -> None:
		if not isinstance(image, np.ndarray):
			raise TypeError("image must be a numpy.ndarray")
		if image.ndim not in (2, 3):
			raise ValueError("image must be 2D (H,W) or 3D (H,W,C)")
		if image.shape[0] == 0 or image.shape[1] == 0:
			raise ValueError("image height and width must be greater than 0")

	@staticmethod
	def _validateTileSize(tileHeight: int, tileWidth: int) -> None:
		if tileHeight <= 0 or tileWidth <= 0:
			raise ValueError("tile_height and tile_width must be greater than 0")

	def gridShapeFor(self, imageShape: tuple[int, ...]) -> tuple[int, int]:
		"""Zwraca liczbę wierszy i kolumn kafelków dla kształtu obrazu."""

		imageHeight, imageWidth = imageShape[0], imageShape[1]
		return ceil(imageHeight / self._tileHeight), ceil(imageWidth / self._tileWidth)

	def paddedShapeFor(self, imageShape: tuple[int, ...]) -> tuple[int, ...]:
		"""Zwraca kształt po dopełnieniu zerami do pełnych granic kafelków."""

		rows, cols = self.gridShapeFor(imageShape)
		paddedHeight = rows * self._tileHeight
		paddedWidth = cols * self._tileWidth
		if len(imageShape) == 2:
			return paddedHeight, paddedWidth
		return paddedHeight, paddedWidth, imageShape[2]

	def padImage(self, image: np.ndarray) -> np.ndarray:
		"""Dopełnia obraz zerami tak, by oba wymiary dzieliły się przez kafelek."""

		self._validateImage(image)
		targetShape = self.paddedShapeFor(image.shape)

		if image.shape == targetShape:
			return image

		padded = np.zeros(targetShape, dtype=image.dtype)
		padded[: image.shape[0], : image.shape[1], ...] = image
		return padded

	@staticmethod
	def cropToShape(image: np.ndarray, outputShape: tuple[int, ...]) -> np.ndarray:
		"""Przycina dopełniony obraz do oryginalnego kształtu."""

		if len(outputShape) == 2:
			return image[: outputShape[0], : outputShape[1]]
		return image[: outputShape[0], : outputShape[1], : outputShape[2]]
