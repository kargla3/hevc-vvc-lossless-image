"""Fabryki komponentow benchmarku."""

from __future__ import annotations

from pathlib import Path

from .config import CurveType, EncoderConfig, TilingConfig
from .encoders.Encoder import Encoder
from .encoders.HEVCEncoder import HEVCEncoder
from .encoders.JPEG2000Encoder import JPEG2000Encoder
from .encoders.JPEGXLEncoder import JPEGXLEncoder
from .encoders.VVCEncoder import VVCEncoder
from .tiling.Tiler import Tiler


def createTiler(config: TilingConfig) -> Tiler:
	"""Tworzy tiler zgodny ze skonfigurowana krzywa."""

	if not isinstance(config, TilingConfig):
		raise TypeError("config must be a TilingConfig instance")

	tilerArguments = {
		"tileHeight": config.tile_height,
		"tileWidth": config.tile_width,
	}
	if config.curve is CurveType.RASTER:
		from .tiling.RasterTiler import RasterTiler

		return RasterTiler(**tilerArguments)
	if config.curve is CurveType.HILBERT:
		from .tiling.HilbertTiler import HilbertTiler

		return HilbertTiler(**tilerArguments)
	if config.curve is CurveType.Z_ORDER:
		from .tiling.ZOrderTiler import ZOrderTiler

		return ZOrderTiler(**tilerArguments)

	raise ValueError(f"Unsupported tiling curve: {config.curve}")


def createEncoder(
	config: EncoderConfig,
	*,
	ffmpegPath: str | Path | None = None,
	encoderPath: str | Path | None = None,
	decoderPath: str | Path | None = None,
) -> Encoder:
	"""Tworzy enkoder zgodny ze skonfigurowanym kodekiem."""

	if not isinstance(config, EncoderConfig):
		raise TypeError("config must be an EncoderConfig instance")

	codec = config.codec.strip().lower().replace("-", "_")
	if codec == "hevc":
		return HEVCEncoder(config, ffmpegPath=str(ffmpegPath) if ffmpegPath else None)
	if codec == "vvc":
		return VVCEncoder(
			config,
			ffmpegPath=str(ffmpegPath) if ffmpegPath else None,
			encoderPath=str(encoderPath) if encoderPath else None,
			decoderPath=str(decoderPath) if decoderPath else None,
		)
	if codec in {"jpeg2000", "jpeg_2000", "jp2"}:
		return JPEG2000Encoder(config)
	if codec in {"jpegxl", "jpeg_xl", "jxl"}:
		return JPEGXLEncoder(config)

	raise ValueError(
		f"Unsupported encoder codec '{config.codec}'. "
		"Supported codecs: hevc, vvc, jpeg2000, jpegxl"
	)


__all__ = ["createEncoder", "createTiler"]
