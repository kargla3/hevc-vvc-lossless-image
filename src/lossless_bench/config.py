"""Modele konfiguracji dla uruchomień benchmarku."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


kDefaultEncoderPreset = "medium"
kDefaultPaddingMode = "constant"
kDefaultOutputDir = "results"


class EncodingMode(str, Enum):
	"""Obsługiwane tryby pracy enkodera."""

	FULL_IMAGE = "full_image"
	INTRA = "intra"
	INTER = "inter"


class CurveType(str, Enum):
	"""Obsługiwane strategie porządkowania kafelków."""

	RASTER = "raster"
	HILBERT = "hilbert"
	Z_ORDER = "z_order"


@dataclass(frozen=True)
class EncoderConfig:
	"""Konfiguracja pojedynczego uruchomienia enkodera."""

	codec: str
	mode: EncodingMode = EncodingMode.FULL_IMAGE
	preset: str = kDefaultEncoderPreset
	extra_params: dict[str, Any] = field(default_factory=dict)

	def __post_init__(self) -> None:
		codec = self.codec.strip()
		preset = self.preset.strip()
		if not codec:
			raise ValueError("codec must not be empty")
		if not preset:
			raise ValueError("preset must not be empty")
		object.__setattr__(self, "codec", codec)
		object.__setattr__(self, "preset", preset)

	def toDict(self) -> dict[str, Any]:
		"""Zwraca reprezentację możliwą do serializacji do JSON."""

		return {
			"codec": self.codec,
			"mode": self.mode.value,
			"preset": self.preset,
			"extra_params": dict(self.extra_params),
		}

	@classmethod
	def fromDict(cls, data: dict[str, Any]) -> "EncoderConfig":
		"""Tworzy konfigurację na podstawie słownika."""

		return cls(
			codec=str(data["codec"]),
			mode=EncodingMode(str(data.get("mode", EncodingMode.FULL_IMAGE.value))),
			preset=str(data.get("preset", kDefaultEncoderPreset)),
			extra_params=dict(data.get("extra_params", {})),
		)


@dataclass(frozen=True)
class TilingConfig:
	"""Konfiguracja dzielenia obrazu na kafelki."""

	tile_width: int
	tile_height: int
	curve: CurveType = CurveType.RASTER
	padding_mode: str = kDefaultPaddingMode

	def __post_init__(self) -> None:
		if self.tile_width <= 0:
			raise ValueError("tile_width must be greater than 0")
		if self.tile_height <= 0:
			raise ValueError("tile_height must be greater than 0")

		padding_mode = self.padding_mode.strip()
		if not padding_mode:
			raise ValueError("padding_mode must not be empty")
		object.__setattr__(self, "padding_mode", padding_mode)

	def toDict(self) -> dict[str, Any]:
		"""Zwraca reprezentację możliwą do serializacji do JSON."""

		return {
			"tile_width": self.tile_width,
			"tile_height": self.tile_height,
			"curve": self.curve.value,
			"padding_mode": self.padding_mode,
		}

	@classmethod
	def fromDict(cls, data: dict[str, Any]) -> "TilingConfig":
		"""Tworzy konfigurację na podstawie słownika."""

		return cls(
			tile_width=int(data["tile_width"]),
			tile_height=int(data["tile_height"]),
			curve=CurveType(str(data.get("curve", CurveType.RASTER.value))),
			padding_mode=str(data.get("padding_mode", kDefaultPaddingMode)),
		)


@dataclass(frozen=True)
class BenchmarkConfig:
	"""Główna konfiguracja benchmarku."""

	image_paths: list[Path]
	encoder_configs: list[EncoderConfig]
	tiling_configs: list[TilingConfig]
	output_dir: Path

	def __post_init__(self) -> None:
		image_paths = [self._normalizePath(path) for path in self.image_paths]
		output_dir = self._normalizePath(self.output_dir)

		if not image_paths:
			raise ValueError("image_paths must not be empty")
		if not self.encoder_configs:
			raise ValueError("encoder_configs must not be empty")
		if not self.tiling_configs:
			raise ValueError("tiling_configs must not be empty")

		object.__setattr__(self, "image_paths", image_paths)
		object.__setattr__(self, "output_dir", output_dir)

	def toDict(self) -> dict[str, Any]:
		"""Zwraca reprezentację możliwą do serializacji do JSON."""

		return {
			"image_paths": [str(path) for path in self.image_paths],
			"encoder_configs": [config.toDict() for config in self.encoder_configs],
			"tiling_configs": [config.toDict() for config in self.tiling_configs],
			"output_dir": str(self.output_dir),
		}

	@classmethod
	def fromDict(cls, data: dict[str, Any]) -> "BenchmarkConfig":
		"""Tworzy konfigurację na podstawie słownika."""

		image_paths = [Path(path) for path in data.get("image_paths", [])]
		encoder_configs = [
			EncoderConfig.fromDict(item) for item in data.get("encoder_configs", [])
		]
		tiling_configs = [
			TilingConfig.fromDict(item) for item in data.get("tiling_configs", [])
		]
		output_dir = Path(data.get("output_dir", kDefaultOutputDir))
		return cls(
			image_paths=image_paths,
			encoder_configs=encoder_configs,
			tiling_configs=tiling_configs,
			output_dir=output_dir,
		)

	@staticmethod
	def _normalizePath(path: Path | str) -> Path:
		"""Normalizuje ścieżkę bez wymuszania sprawdzania istnienia."""

		return Path(path).expanduser()


__all__ = [
	"BenchmarkConfig",
	"CurveType",
	"EncoderConfig",
	"EncodingMode",
	"TilingConfig",
]
