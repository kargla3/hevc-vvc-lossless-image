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
		"ffmpeg", "-y", "-i", video_path, "-start_number", "0", "-pix_fmt", "rgb24",
		os.path.join(frames_dir, "frame_%05d.png"),
	])


def encode_jpeg2000(img: np.ndarray, out_path: str) -> None:
	"""Zapisuje obraz bezstratnie jako JPEG 2000 (odwracalna falka 5/3)."""

	Image.fromarray(img).save(out_path, format="JPEG2000", irreversible=False)


def decode_jpeg2000(path: str) -> np.ndarray:
	"""Wczytuje obraz JPEG 2000 jako tablice NumPy."""

	return np.asarray(Image.open(path))


def encode_jpegxl(img: np.ndarray, out_path: str) -> None:
	"""Zapisuje obraz bezstratnie jako JPEG XL (imagecodecs)."""

	import imagecodecs

	data = imagecodecs.jpegxl_encode(img, lossless=True)
	with open(out_path, "wb") as handle:
		handle.write(data)


def decode_jpegxl(path: str) -> np.ndarray:
	"""Wczytuje obraz JPEG XL jako tablice NumPy."""

	import imagecodecs

	with open(path, "rb") as handle:
		return imagecodecs.jpegxl_decode(handle.read())


kVtmCfgDir = os.path.expanduser("~/tools/vtm/cfg")


def _frames_to_yuv444(frames_dir: str, n_frames: int, yuv_path: str) -> None:
	"""Laczy klatki PNG w jeden surowy strumien planarny YUV444 (kanaly R,G,B jako plaszczyzny)."""

	with open(yuv_path, "wb") as out:
		for i in range(n_frames):
			frame = np.asarray(Image.open(os.path.join(frames_dir, f"frame_{i:05d}.png")))
			out.write(frame.transpose(2, 0, 1).tobytes())  # 3 plaszczyzny H*W


def _yuv444_to_frames(yuv_path: str, frames_dir: str, width: int, height: int) -> None:
	"""Rozpakowuje surowy YUV444 z powrotem na klatki PNG."""

	frame_bytes = 3 * width * height
	with open(yuv_path, "rb") as handle:
		data = handle.read()
	n = len(data) // frame_bytes
	for i in range(n):
		chunk = data[i * frame_bytes:(i + 1) * frame_bytes]
		planes = np.frombuffer(chunk, dtype=np.uint8).reshape(3, height, width)
		frame = planes.transpose(1, 2, 0).copy()
		Image.fromarray(frame).save(os.path.join(frames_dir, f"frame_{i:05d}.png"))


def encode_vvc(frames_dir: str, out_path: str, width: int, height: int, n_frames: int, inter: bool) -> None:
	"""Koduje sekwencje klatek bezstratnie kodekiem VVC (VTM) na planarnym YUV444.

	Flagi lossless potwierdzone eksperymentalnie dla VTM 24.0:
	- --CostMode=lossless: tryb bezstratny (QP'=0, tylko transform skip)
	- --ChromaTS=1 --TransformSkip=1: wymagane dla lossless chroma (DualITree=0)
	- --BDPCM=1: alternatywna sciezka lossless dla blokow z duzym gradientem
	- --DualITree=0: wspolne drzewo partycji dla lumy i chromy (wymagane z ChromaTS)
	- --InternalBitDepth=8: glebokosc wewnetrzna zgodna z 8-bit wejsciem
	- --LFNST=0: Fix bugu VTM 24.0: LFNST=1+DualITree=0+ChromaTS+lossless powoduje
	  assert 'transform skip should be enabled for LS' (IntraSearch.cpp:5264) gdy
	  encoder wybierze LFNST dla CU → lfnstIdx!=0 → tsAllowed=false dla chroma, a
	  BDPCM nie jest testowane dla chroma gdy lfnstIdx!=0 (linia 1628). Fix: LFNST=0.
	- --Log2MaxTbSize=5: Fix wtorny: z LFNST=0 luma takze wymaga tsAllowed=true;
	  Log2MaxTbSize=5 ogranicza max TU do 32x32 → tsAllowed=true zawsze.

	inter=False (all-intra): encoder_intra_vtm.cfg, kazda klatka kodowana osobno
	(enkoder obsługuje 1 klatkę przy IntraPeriod=1 z GOPSize=1); bitstreamy IDR_N_LP
	konkatenowane; dekoder VTM akceptuje taki format.

	inter=True (lowdelay): encoder_lowdelay_vtm.cfg z predykcja B-frame.
	Dodatkowe flagi dla lossless inter-slices:
	- --SBT=0: sub-block transform niekompatybilny z lossless TU split w InterSearch
	- --CTUSize=64 --MaxBTNonISlice=64: ograniczenie rozmiaru bloku inter (unikniecie
	  assert "Not performing the implicit TU split" w xEncodeInterResidualQT)
	- --FastLocalDualTreeMode=0 --EncDbOpt=0: wylaczenie optymalizacji niekompatybilnych
	"""

	import tempfile as _tempfile

	# Flagi wejscia - wspolne dla obu trybow
	common_input = [
		f"--SourceWidth={width}", f"--SourceHeight={height}",
		"--InputChromaFormat=444", "--InputBitDepth=8",
		"--FrameRate=1",
	]
	# Wspolne flagi lossless (dla obu trybow, w tym fix bugu LFNST+ChromaTS)
	common_lossless = [
		"--CostMode=lossless",
		"--ChromaTS=1",
		"--TransformSkip=1",
		"--BDPCM=1",
		"--DualITree=0",
		"--InternalBitDepth=8",
		"--LFNST=0",
		"--Log2MaxTbSize=5",
	]

	if inter:
		# Tryb lowdelay: predykcja inter-klatkowa (B-slices)
		cfg = os.path.join(kVtmCfgDir, "encoder_lowdelay_vtm.cfg")
		# Dodatkowe flagi dla lossless inter-slices w VTM 24.0
		inter_extra = [
			"--SBT=0",
			"--CTUSize=64",
			"--MaxBTNonISlice=64",
			"--FastLocalDualTreeMode=0",
			"--EncDbOpt=0",
		]
		yuv = out_path + ".in.yuv"
		try:
			_frames_to_yuv444(frames_dir, n_frames, yuv)
			_run([
				"EncoderAppStatic", "-c", cfg,
				"-i", yuv, "-b", out_path, "-o", "/dev/null",
				f"--FramesToBeEncoded={n_frames}",
			] + common_input + common_lossless + inter_extra)
		finally:
			if os.path.exists(yuv):
				os.remove(yuv)
	else:
		# Tryb all-intra: kazda klatka kodowana osobno (encoder_intra_vtm obsługuje 1 klatkę)
		# Bitstreamy konkatenowane; dekoder VTM akceptuje sekwencje IDR_N_LP
		cfg = os.path.join(kVtmCfgDir, "encoder_intra_vtm.cfg")
		with open(out_path, "wb") as out_file:
			for i in range(n_frames):
				with _tempfile.NamedTemporaryFile(suffix=".yuv", delete=False) as tmp_yuv, \
				     _tempfile.NamedTemporaryFile(suffix=".vvc", delete=False) as tmp_vvc:
					yuv_path = tmp_yuv.name
					vvc_path = tmp_vvc.name
				try:
					# Zapisz jedną klatkę jako YUV444
					frame = np.asarray(Image.open(
						os.path.join(frames_dir, f"frame_{i:05d}.png")
					))
					with open(yuv_path, "wb") as f:
						f.write(frame.transpose(2, 0, 1).tobytes())
					_run([
						"EncoderAppStatic", "-c", cfg,
						"-i", yuv_path, "-b", vvc_path, "-o", "/dev/null",
						"--FramesToBeEncoded=1",
					] + common_input + common_lossless)
					with open(vvc_path, "rb") as f:
						out_file.write(f.read())
				finally:
					for p in (yuv_path, vvc_path):
						if os.path.exists(p):
							os.remove(p)


def decode_vvc(bitstream: str, frames_dir: str, width: int, height: int) -> None:
	"""Dekoduje strumien VVC (VTM) do klatek PNG."""

	yuv = bitstream + ".out.yuv"
	try:
		_run(["DecoderAppStatic", "-b", bitstream, "-o", yuv])
		_yuv444_to_frames(yuv, frames_dir, width, height)
	finally:
		if os.path.exists(yuv):
			os.remove(yuv)
