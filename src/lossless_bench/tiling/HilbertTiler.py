"""Strategia kafelkowania według krzywej Hilberta."""

from __future__ import annotations

from math import ceil, log2

import numpy as np
from hilbertcurve.hilbertcurve import HilbertCurve

from .Tiler import Tile, Tiler


class HilbertTiler(Tiler):
	"""Przechodzenie po kafelkach oparte o 2D krzywą wypełniającą Hilberta."""

	def splitTiles(self, image: np.ndarray) -> list[Tile]:
		self._validateImage(image)
		paddedImage = self.padImage(image)
		rows, cols = self.gridShapeFor(image.shape)
		coordinates = self._hilbertCoordinates(rows=rows, cols=cols)

		tiles: list[Tile] = []
		for row, col in coordinates:
			r0 = row * self.tileHeight
			r1 = r0 + self.tileHeight
			c0 = col * self.tileWidth
			c1 = c0 + self.tileWidth
			tileData = paddedImage[r0:r1, c0:c1, ...].copy()
			tiles.append(Tile(row=row, col=col, data=tileData))

		return tiles

	def mergeTiles(self, tiles: list[Tile], outputShape: tuple[int, ...]) -> np.ndarray:
		if not tiles:
			raise ValueError("tiles must not be empty")

		rows, cols = self.gridShapeFor(outputShape)
		paddedShape = self.paddedShapeFor(outputShape)
		canvas = np.zeros(paddedShape, dtype=tiles[0].data.dtype)

		expectedTileShape = (
			(self.tileHeight, self.tileWidth)
			if len(paddedShape) == 2
			else (self.tileHeight, self.tileWidth, paddedShape[2])
		)

		for tile in tiles:
			if tile.row < 0 or tile.col < 0 or tile.row >= rows or tile.col >= cols:
				raise ValueError(f"tile index out of bounds: ({tile.row}, {tile.col})")
			if tile.data.shape != expectedTileShape:
				raise ValueError(
					f"invalid tile shape {tile.data.shape}; expected {expectedTileShape}"
				)

			r0 = tile.row * self.tileHeight
			r1 = r0 + self.tileHeight
			c0 = tile.col * self.tileWidth
			c1 = c0 + self.tileWidth
			canvas[r0:r1, c0:c1, ...] = tile.data

		return self.cropToShape(canvas, outputShape)

	@staticmethod
	def _hilbertCoordinates(rows: int, cols: int) -> list[tuple[int, int]]:
		if rows <= 0 or cols <= 0:
			return []

		side = max(rows, cols)
		order = int(ceil(log2(side))) if side > 1 else 1
		hilbert = HilbertCurve(order, 2)

		coordinates: list[tuple[int, int]] = []
		totalPoints = 2 ** (2 * order)
		for distance in range(totalPoints):
			x, y = hilbert.point_from_distance(distance)
			row = y
			col = x
			if row < rows and col < cols:
				coordinates.append((row, col))

		return coordinates
