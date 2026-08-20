"""Kompletny pipeline kompresji jednego obrazu w jednej konfiguracji."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

from .config import EncoderConfig, EncodingMode, TilingConfig
from .encoders.Encoder import Encoder
from .factory import createEncoder, createTiler
from .image.ImageLoader import ImageLoader
from .image.ImageSaver import ImageSaver
from .metrics.CompressionMetrics import CompressionMetrics
from .metrics.MetricsCalculator import MetricsCalculator, measureDuration
from .tiling.Tiler import Tile, Tiler
from .tiling.VideoAssembler import VideoAssembler


class CompressionPipeline:
	"""Wykonuje kodowanie, dekodowanie, rekonstrukcje i pomiar metryk obrazu."""

	def __init__(
		self,
		encoder: Encoder,
		tiler: Tiler | None = None,
		*,
		tilingConfig: TilingConfig | None = None,
		assembler: VideoAssembler | None = None,
		metrics: MetricsCalculator | None = None,
		imageLoader: ImageLoader | None = None,
		imageSaver: ImageSaver | None = None,
	) -> None:
		if not isinstance(encoder, Encoder):
			raise TypeError("encoder must be an Encoder instance")
		if tiler is not None and not isinstance(tiler, Tiler):
			raise TypeError("tiler must be a Tiler instance or None")
		if tilingConfig is not None and not isinstance(tilingConfig, TilingConfig):
			raise TypeError("tilingConfig must be a TilingConfig instance or None")
		if encoder.mode is EncodingMode.FULL_IMAGE and tiler is not None:
			raise ValueError("FULL_IMAGE mode must not use a tiler")
		if encoder.mode is not EncodingMode.FULL_IMAGE and tiler is None:
			raise ValueError(f"{encoder.mode.value} mode requires a tiler")
		if tiler is None and tilingConfig is not None:
			raise ValueError("tilingConfig requires a tiler")
		if tiler is not None and tilingConfig is None:
			raise ValueError("tiler requires a tilingConfig")

		self._encoder = encoder
		self._tiler = tiler
		self._tilingConfig = tilingConfig
		self._assembler = assembler or VideoAssembler()
		self._metrics = metrics or MetricsCalculator()
		self._imageLoader = imageLoader or ImageLoader()
		self._imageSaver = imageSaver or ImageSaver()

	@property
	def encoder(self) -> Encoder:
		"""Zwraca enkoder uzywany przez pipeline."""

		return self._encoder

	@property
	def tiler(self) -> Tiler | None:
		"""Zwraca skonfigurowany tiler albo None dla trybu pelnego obrazu."""

		return self._tiler

	def runPipeline(
		self,
		imagePath: str | Path,
		outputDir: str | Path,
		*,
		saveReconstruction: bool = False,
	) -> CompressionMetrics:
		"""Wykonuje kompletny eksperyment kompresji."""

		imagePath = Path(imagePath).expanduser()
		outputDirectory = Path(outputDir).expanduser()
		image = self._imageLoader.loadImage(imagePath)
		outputDirectory.mkdir(parents=True, exist_ok=True)
		self._prepareWorkDirectories(outputDirectory)

		sourcePath, tiles = self._prepareSource(image, outputDirectory)
		bitstreamPath = outputDirectory / "bitstream"
		decodedDirectory = outputDirectory / "decoded"

		with measureDuration() as encodeDuration:
			encodedPath = self._encoder.encode(sourcePath, bitstreamPath)

		with measureDuration() as decodeDuration:
			decodedPath = self._encoder.decode(encodedPath, decodedDirectory)

		restored = self._restoreImage(
			decodedPath=decodedPath,
			tiles=tiles,
			outputShape=image.shape,
		)
		if saveReconstruction:
			self._imageSaver.saveImage(restored, outputDirectory / "reconstructed.png")

		return self._metrics.measureCompression(
			original=image,
			restored=restored,
			compressedBytes=self._metrics.measureBitstreamBytes(encodedPath),
			encodeTime=encodeDuration.seconds,
			decodeTime=decodeDuration.seconds,
			imagePath=imagePath,
			encoderName=self._encoder.getName(),
			tilingConfig=self._tilingConfig,
			tileCount=len(tiles) if tiles is not None else 1,
		)

	def _prepareSource(
		self,
		image: np.ndarray,
		outputDirectory: Path,
	) -> tuple[Path, list[Tile] | None]:
		"""Zapisuje zrodlo enkodera jako obraz albo uporzadkowana sekwencje klatek."""

		if self._tiler is None:
			sourcePath = outputDirectory / "source.png"
			self._imageSaver.saveImage(image, sourcePath)
			return sourcePath, None

		tiles = self._tiler.splitTiles(image)
		framesPath = self._assembler.framesToVideo(tiles, outputDirectory / "frames")
		return framesPath, tiles

	def _restoreImage(
		self,
		*,
		decodedPath: Path,
		tiles: list[Tile] | None,
		outputShape: tuple[int, ...],
	) -> np.ndarray:
		"""Wczytuje zdekodowane klatki i odtwarza geometrie oryginalnego obrazu."""

		frames = self._assembler.videoToFrames(decodedPath)
		if tiles is None:
			if len(frames) != 1:
				raise ValueError(f"Expected one decoded frame, got {len(frames)}")
			return frames[0]

		if len(frames) != len(tiles):
			raise ValueError(
				f"Expected {len(tiles)} decoded frames, got {len(frames)}"
			)
		restoredTiles = [
			Tile(row=tile.row, col=tile.col, data=frame)
			for tile, frame in zip(tiles, frames)
		]
		return self._tiler.mergeTiles(restoredTiles, outputShape)

	@staticmethod
	def _prepareWorkDirectories(outputDirectory: Path) -> None:
		"""Usuwa tylko katalogi zarzadzane przez to uruchomienie pipeline'u."""

		for name in ("frames", "decoded"):
			path = outputDirectory / name
			if path.exists():
				if not path.is_dir():
					raise NotADirectoryError(f"Expected a directory, got a file: {path}")
				shutil.rmtree(path)



def buildPipeline(
	encoderConfig: EncoderConfig,
	tilingConfig: TilingConfig | None = None,
	*,
	ffmpegPath: str | Path | None = None,
	encoderPath: str | Path | None = None,
	decoderPath: str | Path | None = None,
) -> CompressionPipeline:
	"""Buduje pipeline na podstawie konfiguracji enkodera i opcjonalnego tilingu."""

	encoder = createEncoder(
		encoderConfig,
		ffmpegPath=ffmpegPath,
		encoderPath=encoderPath,
		decoderPath=decoderPath,
	)
	tiler = createTiler(tilingConfig) if tilingConfig is not None else None
	return CompressionPipeline(
		encoder=encoder,
		tiler=tiler,
		tilingConfig=tilingConfig,
	)


__all__ = ["CompressionPipeline", "buildPipeline"]
