"""Enkoder JPEG 2000 oparty o imagecodecs (OpenJPEG)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .Encoder import Encoder


kBitstreamSuffix = ".jp2"
kDefaultCodecFormat = "JP2"
kReversibleLevel = 0
kSupportedCodecFormats = {"JP2", "J2K"}


class JPEG2000Encoder(Encoder):
	"""Koduje obrazy bezstratnie w JPEG 2000 przy użyciu ``imagecodecs``.

	Kompresja jest zawsze odwracalna: transformata falkowa 5/3 i brak
	kwantyzacji (``reversible=True``, ``level=0``) dają rekonstrukcję identyczną
	co do piksela. Kodek nie ma predykcji międzyklatkowej, więc tryb z
	konfiguracji nie zmienia sposobu kodowania — katalog klatek jest kodowany
	jako niezależne bitstreamy, po jednym na kafelek.

	Parametry z ``extra_params``:

	- ``codec_format`` — ``JP2`` (kontener, domyślnie) albo ``J2K`` (sam
	  strumień kodowy, bez narzutu kontenera),
	- ``resolutions`` — liczba poziomów rozkładu falkowego,
	- ``mct`` — transformata międzyskładowa (domyślnie włączona dla RGB,
	  w wersji odwracalnej RCT).
	"""

	def __init__(self, config) -> None:
		super().__init__(config)
		self._codecFormat = str(
			self.extraParams.get("codec_format", kDefaultCodecFormat)
		).upper()
		if self._codecFormat not in kSupportedCodecFormats:
			raise ValueError(
				f"Unsupported codec_format '{self._codecFormat}'. "
				f"Supported values: {sorted(kSupportedCodecFormats)}"
			)

		self._resolutions = self.extraParams.get("resolutions")
		self._mct = self.extraParams.get("mct")

	def encode(self, src: str | Path, dst: str | Path) -> Path:
		"""Koduje obraz albo katalog klatek do bitstreamów JPEG 2000."""

		source = self._normalizePath(src)
		frames = self._collectFrames(source)
		self._inspectFrames(frames)

		return self._encodeFrameFiles(
			source,
			frames,
			dst,
			suffix=kBitstreamSuffix,
			encodeFrame=self._encodeFrame,
		)

	def decode(self, src: str | Path, dst: str | Path) -> Path:
		"""Dekoduje bitstreamy JPEG 2000 do katalogu klatek PNG."""

		source = self._normalizePath(src)
		return self._decodeFrameFiles(
			source,
			dst,
			suffix=kBitstreamSuffix,
			decodeFrame=self._decodeFrame,
		)

	def getName(self) -> str:
		"""Zwraca nazwę enkodera używaną w raportach."""

		return f"JPEG 2000 ({self._codecFormat}, reversible)"

	def _encodeFrame(self, frame: np.ndarray) -> bytes:
		"""Koduje pojedynczą klatkę do bezstratnego bitstreamu JPEG 2000."""

		codec = self._loadCodec()
		options: dict[str, object] = {}
		if self._resolutions is not None:
			options["resolutions"] = int(self._resolutions)
		if self._mct is not None:
			options["mct"] = bool(self._mct)

		return bytes(
			codec.jpeg2k_encode(
				frame,
				level=kReversibleLevel,
				reversible=True,
				codecformat=self._codecFormat,
				**options,
			)
		)

	def _decodeFrame(self, bitstream: bytes) -> np.ndarray:
		"""Dekoduje pojedynczy bitstream JPEG 2000 do tablicy NumPy."""

		return self._loadCodec().jpeg2k_decode(bitstream)

	@staticmethod
	def _loadCodec():
		"""Importuje ``imagecodecs`` z czytelnym komunikatem przy braku pakietu."""

		try:
			import imagecodecs
		except ImportError as error:
			raise ImportError(
				"JPEG 2000 encoding requires the 'imagecodecs' package. "
				"Install it with: pip install imagecodecs"
			) from error

		if not imagecodecs.JPEG2K.available:
			raise RuntimeError(
				"The installed 'imagecodecs' build has no JPEG 2000 support."
			)

		return imagecodecs


__all__ = ["JPEG2000Encoder"]
