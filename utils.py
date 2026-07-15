"""Funkcje pomocnicze benchmarku kompresji bezstratnej."""

from __future__ import annotations

import math

import numpy as np


TILE = 256


def grid_shape(img_shape: tuple, tile: int) -> tuple[int, int]:
	"""Zwraca liczbe wierszy i kolumn kafelkow dla ksztaltu obrazu."""

	h, w = img_shape[0], img_shape[1]
	return math.ceil(h / tile), math.ceil(w / tile)


def pad_to_grid(img: np.ndarray, tile: int) -> np.ndarray:
	"""Dopelnia obraz zerami do wielokrotnosci rozmiaru kafelka."""

	rows, cols = grid_shape(img.shape, tile)
	ph, pw = rows * tile, cols * tile
	if (ph, pw) == (img.shape[0], img.shape[1]):
		return img
	padded = np.zeros((ph, pw) + img.shape[2:], dtype=img.dtype)
	padded[: img.shape[0], : img.shape[1]] = img
	return padded


def split_tiles(img: np.ndarray, tile: int) -> list[np.ndarray]:
	"""Dzieli obraz na kafelki w kolejnosci row-major."""

	padded = pad_to_grid(img, tile)
	rows, cols = grid_shape(img.shape, tile)
	tiles: list[np.ndarray] = []
	for r in range(rows):
		for c in range(cols):
			tiles.append(padded[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile].copy())
	return tiles


def merge_tiles(tiles: list[np.ndarray], rows: int, cols: int, tile: int) -> np.ndarray:
	"""Skleja kafelki row-major w obraz z paddingiem."""

	first = tiles[0]
	canvas = np.zeros((rows * tile, cols * tile) + first.shape[2:], dtype=first.dtype)
	i = 0
	for r in range(rows):
		for c in range(cols):
			canvas[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile] = tiles[i]
			i += 1
	return canvas


def crop_to_shape(img: np.ndarray, shape: tuple) -> np.ndarray:
	"""Przycina obraz z paddingiem do oryginalnego ksztaltu."""

	return img[: shape[0], : shape[1]]
