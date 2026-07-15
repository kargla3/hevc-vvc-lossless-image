"""Funkcje pomocnicze benchmarku kompresji bezstratnej."""

from __future__ import annotations

import importlib.util
import math
import os
import shutil
import subprocess

import numpy as np
from PIL import Image
from hilbertcurve.hilbertcurve import HilbertCurve


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


def raster_order(rows: int, cols: int) -> list[int]:
	"""Kolejnosc rastrowa (row-major) — tozsamosc."""

	return list(range(rows * cols))


def hilbert_order(rows: int, cols: int) -> list[int]:
	"""Kolejnosc kafelkow wg 2D krzywej Hilberta (indeksy row-major)."""

	side = max(rows, cols)
	p = max(1, math.ceil(math.log2(side))) if side > 1 else 1
	hilbert = HilbertCurve(p, 2)
	seq: list[int] = []
	for distance in range(2 ** (2 * p)):
		x, y = hilbert.point_from_distance(distance)  # x=kolumna, y=wiersz
		if y < rows and x < cols:
			seq.append(y * cols + x)
	return seq


def zorder_order(rows: int, cols: int) -> list[int]:
	"""Kolejnosc kafelkow wg krzywej Z-order (indeksy row-major)."""

	def interleave(r: int, c: int) -> int:
		bits = max(r.bit_length(), c.bit_length())
		z = 0
		for i in range(bits):
			z |= ((c >> i) & 1) << (2 * i)
			z |= ((r >> i) & 1) << (2 * i + 1)
		return z

	indexed = [(r * cols + c, interleave(r, c)) for r in range(rows) for c in range(cols)]
	indexed.sort(key=lambda pair: pair[1])
	return [row_major for row_major, _ in indexed]


def reorder(items: list, order: list[int]) -> list:
	"""Ustawia elementy w kolejnosci zadanej przez `order`."""

	return [items[i] for i in order]


def unreorder(seq: list, order: list[int]) -> list:
	"""Odwraca `reorder`: sekwencja wg krzywej -> kolejnosc row-major."""

	restored: list = [None] * len(order)
	for seq_pos, row_major in enumerate(order):
		restored[row_major] = seq[seq_pos]
	return restored


ORDERS = {
	"raster": raster_order,
	"hilbert": hilbert_order,
	"zorder": zorder_order,
}


def bits_per_pixel(comp_bytes: int, width: int, height: int) -> float:
	"""Bity na piksel obrazu."""

	return comp_bytes * 8 / (width * height)


def compression_ratio(orig_bytes: int, comp_bytes: int) -> float:
	"""Stosunek rozmiaru surowego do skompresowanego."""

	return orig_bytes / comp_bytes


def verify_lossless(a: np.ndarray, b: np.ndarray) -> bool:
	"""Sprawdza, czy rekonstrukcja jest identyczna z oryginalem."""

	return bool(np.array_equal(a, b))


def has_tool(name: str) -> bool:
	"""Czy narzedzie CLI jest dostepne w PATH."""

	return shutil.which(name) is not None


def has_module(name: str) -> bool:
	"""Czy modul Pythona jest importowalny."""

	return importlib.util.find_spec(name) is not None


def _run(cmd: list[str]) -> None:
	"""Uruchamia polecenie, podnosi wyjatek z stderr przy bledzie."""

	result = subprocess.run(cmd, capture_output=True, text=True)
	if result.returncode != 0:
		raise RuntimeError(f"Polecenie zawiodlo: {' '.join(cmd)}\n{result.stderr}")


def write_frames(tiles: list[np.ndarray], frames_dir: str) -> None:
	"""Zapisuje kafelki jako kolejne klatki PNG frame_00000.png..."""

	for i, tile in enumerate(tiles):
		Image.fromarray(tile).save(os.path.join(frames_dir, f"frame_{i:05d}.png"))


def read_frames(frames_dir: str, n: int) -> list[np.ndarray]:
	"""Wczytuje n klatek PNG w kolejnosci."""

	return [
		np.asarray(Image.open(os.path.join(frames_dir, f"frame_{i:05d}.png")))
		for i in range(n)
	]


def encode_hevc(frames_dir: str, out_path: str, inter: bool) -> None:
	"""Koduje sekwencje klatek PNG bezstratnie kodekiem HEVC (libx265)."""

	params = "lossless=1:log-level=error"
	if not inter:
		params += ":keyint=1"
	_run([
		"ffmpeg", "-y", "-framerate", "1", "-start_number", "0",
		"-i", os.path.join(frames_dir, "frame_%05d.png"),
		"-c:v", "libx265", "-pix_fmt", "gbrp", "-x265-params", params,
		out_path,
	])


def decode_hevc(video_path: str, frames_dir: str) -> None:
	"""Dekoduje wideo HEVC z powrotem do klatek PNG."""

	_run([
		"ffmpeg", "-y", "-i", video_path, "-start_number", "0",
		os.path.join(frames_dir, "frame_%05d.png"),
	])
