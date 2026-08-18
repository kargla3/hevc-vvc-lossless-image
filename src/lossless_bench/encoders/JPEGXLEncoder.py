"""Enkoder JPEG XL oparty o imagecodecs (libjxl)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .Encoder import Encoder


kBitstreamSuffix = ".jxl"
kDefaultEffort = 7
kMinEffort = 1
kMaxEffort = 9
kEffortPerPreset = {
	"ultrafast": 1,
	"superfast": 2,
	"veryfast": 3,
	"faster": 4,
	"fast": 5,
	"medium": 7,
	"slow": 8,
	"slower": 9,
	"veryslow": 9,
	"placebo": 9,
}


class JPEGXLEncoder(Encoder):
	"""Koduje obrazy bezstratnie w JPEG XL przy użyciu ``imagecodecs``.

	Kompresja jest zawsze bezstratna (``lossless=True``). Kodek nie ma predykcji
	międzyklatkowej, więc tryb z konfiguracji nie zmienia sposobu kodowania —
	katalog klatek jest kodowany jako niezależne bitstreamy, po jednym na
	kafelek.

	Wysiłek kodowania (1 — najszybciej, 9 — najmniejszy plik) pochodzi z
	``extra_params.effort``, a w razie jego braku jest wyprowadzany z presetu
	z konfiguracji (``medium`` odpowiada wysiłkowi 7).
	"""

	def __init__(self, config) -> None:
		super().__init__(config)
		self._effort = self._resolveEffort()

	def encode(self, src: str | Path, dst: str | Path) -> Path:
		"""Koduje obraz albo katalog klatek do bitstreamów JPEG XL."""

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
		"""Dekoduje bitstreamy JPEG XL do katalogu klatek PNG."""

		source = self._normalizePath(src)
		return self._decodeFrameFiles(
			source,
			dst,
			suffix=kBitstreamSuffix,
			decodeFrame=self._decodeFrame,
		)

	def getName(self) -> str:
		"""Zwraca nazwę enkodera używaną w raportach."""

		return f"JPEG XL (lossless, effort={self._effort})"

	@property
	def effort(self) -> int:
		"""Zwraca wysiłek kodowania użyty przez enkoder."""

		return self._effort

	def _encodeFrame(self, frame: np.ndarray) -> bytes:
		"""Koduje pojedynczą klatkę do bezstratnego bitstreamu JPEG XL."""

		codec = self._loadCodec()
		return bytes(
			codec.jpegxl_encode(
				frame,
				lossless=True,
				effort=self._effort,
			)
		)

	def _decodeFrame(self, bitstream: bytes) -> np.ndarray:
		"""Dekoduje pojedynczy bitstream JPEG XL do tablicy NumPy."""

		return self._loadCodec().jpegxl_decode(bitstream)

	def _resolveEffort(self) -> int:
		"""Ustala wysiłek kodowania z ``extra_params`` albo z presetu."""

		configuredEffort = self.extraParams.get("effort")
		if configuredEffort is None:
			configuredEffort = kEffortPerPreset.get(self.preset.lower(), kDefaultEffort)

		effort = int(configuredEffort)
		if not kMinEffort <= effort <= kMaxEffort:
			raise ValueError(
				f"effort must be between {kMinEffort} and {kMaxEffort}, got {effort}"
			)

		return effort

	@staticmethod
	def _loadCodec():
		"""Importuje ``imagecodecs`` z czytelnym komunikatem przy braku pakietu."""

		try:
			import imagecodecs
		except ImportError as error:
			raise ImportError(
				"JPEG XL encoding requires the 'imagecodecs' package. "
				"Install it with: pip install imagecodecs"
			) from error

		if not imagecodecs.JPEGXL.available:
			raise RuntimeError(
				"The installed 'imagecodecs' build has no JPEG XL support."
			)

		return imagecodecs


__all__ = ["JPEGXLEncoder"]
