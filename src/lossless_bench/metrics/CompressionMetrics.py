"""Wynik pojedynczego pomiaru kompresji."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import TilingConfig


@dataclass(frozen=True)
class ImageDifference:
	"""Skala różnic między obrazem oryginalnym a odtworzonym."""

	is_lossless: bool
	max_diff: int
	mean_diff: float


@dataclass(frozen=True)
class CompressionMetrics:
	"""Metryki jednego uruchomienia enkodera na jednym obrazie."""

	original_bytes: int
	compressed_bytes: int
	bpp: float
	ratio: float
	encode_time_s: float
	decode_time_s: float
	is_lossless: bool
	image_path: Path
	encoder_name: str
	tiling_config: TilingConfig | None
	max_diff: int
	mean_diff: float
	tile_count: int
	width: int
	height: int
	channels: int

	def toDict(self) -> dict[str, Any]:
		"""Zwraca płaski słownik gotowy na wiersz CSV albo JSON.

		Konfiguracja kafelkowania jest rozwijana do osobnych kolumn, bo
		zagnieżdżony słownik nie zapisałby się sensownie do CSV. W trybie
		``full_image`` te kolumny mają wartość ``None``.
		"""

		row: dict[str, Any] = {
			"image_path": str(self.image_path),
			"encoder_name": self.encoder_name,
			"width": self.width,
			"height": self.height,
			"channels": self.channels,
			"tile_count": self.tile_count,
			"original_bytes": self.original_bytes,
			"compressed_bytes": self.compressed_bytes,
			"bpp": self.bpp,
			"ratio": self.ratio,
			"encode_time_s": self.encode_time_s,
			"decode_time_s": self.decode_time_s,
			"is_lossless": self.is_lossless,
			"max_diff": self.max_diff,
			"mean_diff": self.mean_diff,
		}

		if self.tiling_config is None:
			row["tile_width"] = None
			row["tile_height"] = None
			row["curve"] = None
			row["padding_mode"] = None
		else:
			row["tile_width"] = self.tiling_config.tile_width
			row["tile_height"] = self.tiling_config.tile_height
			row["curve"] = self.tiling_config.curve.value
			row["padding_mode"] = self.tiling_config.padding_mode

		return row


__all__ = ["CompressionMetrics", "ImageDifference"]
