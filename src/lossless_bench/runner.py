"""Uruchamianie macierzy eksperymentow benchmarku."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .config import BenchmarkConfig, EncoderConfig, EncodingMode, TilingConfig
from .metrics.CompressionMetrics import CompressionMetrics
from .pipeline import CompressionPipeline, buildPipeline


PipelineBuilder = Callable[
	[EncoderConfig, TilingConfig | None],
	CompressionPipeline,
]


@dataclass(frozen=True)
class BenchmarkFailure:
	"""Opis nieudanego eksperymentu benchmarku."""

	experiment: str
	error_type: str
	error: str


class BenchmarkRunner:
	"""Uruchamia eksperymenty dla obrazow i konfiguracji kodekow."""

	def __init__(
		self,
		config: BenchmarkConfig,
		*,
		pipelineBuilder: PipelineBuilder = buildPipeline,
		saveReconstruction: bool = False,
	) -> None:
		if not isinstance(config, BenchmarkConfig):
			raise TypeError("config must be a BenchmarkConfig instance")
		if not callable(pipelineBuilder):
			raise TypeError("pipelineBuilder must be callable")

		self._config = config
		self._pipelineBuilder = pipelineBuilder
		self._saveReconstruction = saveReconstruction
		self._results: list[CompressionMetrics] = []
		self._failures: list[BenchmarkFailure] = []

	@property
	def config(self) -> BenchmarkConfig:
		"""Zwraca konfiguracje uzywana przez runner."""

		return self._config

	@property
	def results(self) -> list[CompressionMetrics]:
		"""Zwraca wyniki ostatniego uruchomienia."""

		return list(self._results)

	@property
	def failures(self) -> list[BenchmarkFailure]:
		"""Zwraca bledy eksperymentow z ostatniego uruchomienia."""

		return list(self._failures)

	def runAll(self) -> list[CompressionMetrics]:
		"""Uruchamia wszystkie eksperymenty i zwraca ich wyniki."""

		results: list[CompressionMetrics] = []
		failures: list[BenchmarkFailure] = []
		for imageIndex, imagePath in enumerate(self._config.image_paths):
			for encoderConfig in self._config.encoder_configs:
				for tilingConfig in self._tilingConfigsFor(encoderConfig):
					outputDirectory = self._outputDirectory(
						imageIndex=imageIndex,
						imagePath=imagePath,
						encoderConfig=encoderConfig,
						tilingConfig=tilingConfig,
					)
					experiment = str(outputDirectory.relative_to(self._config.output_dir))
					try:
						pipeline = self._pipelineBuilder(encoderConfig, tilingConfig)
						results.append(
							pipeline.runPipeline(
								imagePath=imagePath,
								outputDir=outputDirectory,
								saveReconstruction=self._saveReconstruction,
							)
						)
					except Exception as error:  # noqa: BLE001 - report and continue
						failures.append(
							BenchmarkFailure(
								experiment=experiment,
								error_type=type(error).__name__,
								error=str(error),
							)
						)

		self._results = results
		self._failures = failures
		return list(results)

	def resultsToDataFrame(self, results: list[CompressionMetrics] | None = None) -> Any:
		"""Konwertuje wyniki do pandas.DataFrame."""

		selectedResults = self._results if results is None else results
		try:
			import pandas as pd
		except ImportError as error:
			raise ImportError(
				"Converting benchmark results to a DataFrame requires pandas."
			) from error

		return pd.DataFrame(result.toDict() for result in selectedResults)

	def _tilingConfigsFor(
		self,
		encoderConfig: EncoderConfig,
	) -> list[TilingConfig | None]:
		"""Zwraca konfiguracje tilingu dla trybu danego enkodera."""

		if encoderConfig.mode is EncodingMode.FULL_IMAGE:
			return [None]
		return list(self._config.tiling_configs)

	def _outputDirectory(
		self,
		*,
		imageIndex: int,
		imagePath: Path,
		encoderConfig: EncoderConfig,
		tilingConfig: TilingConfig | None,
	) -> Path:
		"""Buduje stabilna sciezke katalogu dla jednego eksperymentu."""

		imageName = f"{imageIndex:04d}_{self._slug(imagePath.stem)}"
		encoderName = self._slug(
			f"{encoderConfig.codec}_{encoderConfig.mode.value}_{encoderConfig.preset}"
		)
		if tilingConfig is None:
			tilingName = "full_image"
		else:
			tilingName = self._slug(
				f"{tilingConfig.curve.value}_"
				f"{tilingConfig.tile_width}x{tilingConfig.tile_height}"
			)

		return self._config.output_dir / imageName / encoderName / tilingName

	@staticmethod
	def _slug(value: str) -> str:
		"""Normalizuje fragment sciezki do bezpiecznej nazwy katalogu."""

		normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
		return normalized.strip("._") or "unnamed"


__all__ = ["BenchmarkFailure", "BenchmarkRunner", "PipelineBuilder"]
