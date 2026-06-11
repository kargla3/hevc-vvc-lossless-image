"""Strategia kafelkowania Z-order (Morton)."""

from __future__ import annotations

import numpy as np

from .Tiler import Tile, Tiler


class ZOrderTiler(Tiler):
	"""Przechodzenie po kafelkach oparte o krzywą Mortona (Z-order)."""

	def splitTiles(self, image: np.ndarray) -> list[Tile]:
		self._validateImage(image)
		paddedImage = self.padImage(image)
		rows, cols = self.gridShapeFor(image.shape)

		coordinates = [(row, col) for row in range(rows) for col in range(cols)]
		coordinates.sort(key=lambda rc: self._mortonCode(row=rc[0], col=rc[1]))

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
	def _mortonCode(row: int, col: int) -> int:
		return (ZOrderTiler._part1By1(col) << 1) | ZOrderTiler._part1By1(row)

	@staticmethod
	def _part1By1(value: int) -> int:
		value &= 0x0000FFFF
		value = (value | (value << 8)) & 0x00FF00FF
		value = (value | (value << 4)) & 0x0F0F0F0F
		value = (value | (value << 2)) & 0x33333333
		value = (value | (value << 1)) & 0x55555555
		return value
