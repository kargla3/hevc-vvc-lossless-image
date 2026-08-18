"""Liczenie metryk kompresji na gotowych danych."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterator

import numpy as np

from ..config import TilingConfig
from .CompressionMetrics import CompressionMetrics, ImageDifference


@dataclass
class Duration:
	"""Czas trwania zmierzonego bloku kodu, w sekundach."""

	seconds: float = 0.0


@contextmanager
def measureDuration() -> Iterator[Duration]:
	"""Mierzy czas wykonania bloku i zapisuje go w polu ``seconds``.

	Czas jest zapisywany także wtedy, gdy blok rzuci wyjątkiem, dzięki czemu
	nieudane kodowanie nadal daje się opisać w logach.
	"""

	duration = Duration()
	started = perf_counter()
	try:
		yield duration
	finally:
		duration.seconds = perf_counter() - started


class MetricsCalculator:
	"""Liczy metryki kompresji na podstawie gotowych danych.

	Klasa nie uruchamia enkoderów ani nie zna kolejności operacji — dostaje
	obrazy, rozmiary i zmierzone czasy, a zwraca ``CompressionMetrics``.
	"""

	kBitstreamSuffixes = {".265", ".266", ".jp2", ".j2k", ".jxl"}

	def verifyLossless(self, original: np.ndarray, restored: np.ndarray) -> bool:
		"""Sprawdza, czy odtworzony obraz jest identyczny z oryginałem."""

		self._validatePair(original, restored)
		return bool(np.array_equal(original, restored))

	def compareImages(self, original: np.ndarray, restored: np.ndarray) -> ImageDifference:
		"""Porównuje obrazy i zwraca skalę różnic.

		Różnice liczone są na ``int32``, żeby odejmowanie próbek ``uint8``
		nie zawinęło się do dużej liczby dodatniej.
		"""

		self._validatePair(original, restored)
		difference = np.abs(original.astype(np.int32) - restored.astype(np.int32))
		return ImageDifference(
			is_lossless=bool(np.array_equal(original, restored)),
			max_diff=int(difference.max()),
			mean_diff=float(difference.mean()),
		)

	def measureBitstreamBytes(self, path: str | Path) -> int:
		"""Sumuje rozmiar bitstreamu, pomijając pliki pomocnicze.

		Ścieżka może wskazywać pojedynczy plik albo katalog z osobnym
		bitstreamem na kafelek. W katalogu liczone są wyłącznie pliki
		o rozszerzeniach z ``kBitstreamSuffixes`` — dzięki temu manifest
		``meta.json`` zapisywany przez ``VVCEncoder`` nie zawyża wyniku.
		"""

		bitstreamPath = Path(path).expanduser()
		if not bitstreamPath.exists():
			raise FileNotFoundError(f"Bitstream not found: {bitstreamPath}")

		if bitstreamPath.is_file():
			return bitstreamPath.stat().st_size

		bitstreamFiles = [
			item
			for item in bitstreamPath.rglob("*")
			if item.is_file() and item.suffix.lower() in self.kBitstreamSuffixes
		]
		if not bitstreamFiles:
			raise ValueError(
				f"No bitstream files found in {bitstreamPath}. "
				f"Expected extensions: {sorted(self.kBitstreamSuffixes)}"
			)

		return sum(item.stat().st_size for item in bitstreamFiles)

	def measureCompression(
		self,
		*,
		original: np.ndarray,
		restored: np.ndarray,
		compressedBytes: int,
		encodeTime: float,
		decodeTime: float,
		imagePath: str | Path,
		encoderName: str,
		tilingConfig: TilingConfig | None = None,
		tileCount: int = 1,
	) -> CompressionMetrics:
		"""Składa komplet metryk dla jednego uruchomienia enkodera.

		``bpp`` liczone jest względem wymiarów oryginału, a nie obrazu
		z paddingiem — inaczej kafelkowanie sztucznie zaniżałoby wynik.
		Wszystkie argumenty są nazwane, bo jest ich zbyt wiele, żeby
		kolejność pozycyjna pozostała czytelna.
		"""

		if compressedBytes <= 0:
			raise ValueError(
				f"compressedBytes must be greater than 0, got {compressedBytes}"
			)
		if tileCount <= 0:
			raise ValueError(f"tileCount must be greater than 0, got {tileCount}")
		if encodeTime < 0 or decodeTime < 0:
			raise ValueError(
				f"Times must not be negative, got encode={encodeTime}, decode={decodeTime}"
			)

		difference = self.compareImages(original, restored)
		height, width, channels = self._describeShape(original)

		originalBytes = int(original.nbytes)
		pixels = height * width

		return CompressionMetrics(
			original_bytes=originalBytes,
			compressed_bytes=int(compressedBytes),
			bpp=compressedBytes * 8 / pixels,
			ratio=originalBytes / compressedBytes,
			encode_time_s=float(encodeTime),
			decode_time_s=float(decodeTime),
			is_lossless=difference.is_lossless,
			image_path=Path(imagePath),
			encoder_name=encoderName,
			tiling_config=tilingConfig,
			max_diff=difference.max_diff,
			mean_diff=difference.mean_diff,
			tile_count=int(tileCount),
			width=width,
			height=height,
			channels=channels,
		)

	def _validatePair(self, original: np.ndarray, restored: np.ndarray) -> None:
		"""Sprawdza, czy para obrazów w ogóle nadaje się do porównania.

		Niezgodność jest błędem, a nie wynikiem ``False`` — inaczej pomyłka
		w rekonstrukcji wyglądałaby w wynikach identycznie jak kompresja
		stratna i mogłaby przejść niezauważona.
		"""

		self._describeShape(original)
		self._describeShape(restored)

		if original.shape != restored.shape:
			raise ValueError(
				f"Image shapes differ: {original.shape} vs {restored.shape}"
			)
		if original.dtype != restored.dtype:
			raise ValueError(
				f"Image dtypes differ: {original.dtype} vs {restored.dtype}"
			)

	def _describeShape(self, image: np.ndarray) -> tuple[int, int, int]:
		"""Zwraca wysokość, szerokość i liczbę kanałów tablicy obrazu.

		Tablica dwuwymiarowa to obraz monochromatyczny, czyli jeden kanał —
		taki kształt zwraca ``ImageLoader`` dla trybu ``L``.
		"""

		if image.ndim == 2:
			height, width = image.shape
			channels = 1
		elif image.ndim == 3:
			height, width, channels = image.shape
		else:
			raise ValueError(
				f"Expected a 2D or 3D image array, got shape {image.shape}"
			)

		if height <= 0 or width <= 0 or channels <= 0:
			raise ValueError(f"Image must not be empty, got shape {image.shape}")

		return height, width, channels


__all__ = ["Duration", "MetricsCalculator", "measureDuration"]
