# Benchmark bezstratnej kompresji kodekami wideo — Plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zbudować prosty benchmark porównujący bezstratną kompresję dużych obrazów kodekami wideo (HEVC, VVC) w różnych trybach kafelkowania (raster/Hilbert/Z-order) z kompresorami obrazów (JPEG 2000, JPEG XL).

**Architecture:** Cztery proste skrypty Pythona bez klas i pakietów. `utils.py` zawiera wszystkie funkcje pomocnicze (tiling, porządki krzywych, wywołania kodeków, metryki). `generate_images.py` przygotowuje obrazy, `benchmark.py` wykonuje macierz eksperymentów do CSV, `report.py` rysuje wykresy. Kodeki wideo działają na sekwencji klatek-kafelków przez ffmpeg (HEVC) i VTM (VVC); JPEG 2000 przez Pillow, JPEG XL przez imagecodecs.

**Tech Stack:** Python 3.10, numpy, Pillow, hilbertcurve, pandas, matplotlib, imagecodecs (JPEG XL), pytest. Narzędzia systemowe: ffmpeg+libx265 (HEVC), libopenjpeg (JPEG 2000 przez Pillow), VTM `EncoderAppStatic`/`DecoderAppStatic` (VVC, budowane ze źródeł).

## Global Constraints

- Kod prosty: bez klas, bez pakietów, bez `src/`/`__init__.py`. Zwykłe funkcje, `snake_case`. Każdy skrypt < ~200 linii.
- Komentarze i komunikaty dla użytkownika po polsku (styl repo).
- Wejście: tylko zdjęcia z `photos/`. JPG jest stratny — jego zdekodowane piksele traktujemy jako "oryginał".
- Obrazy naturalne: pełny rozmiar (~4000×6000), bez skalowania.
- Rozmiar kafelka: `TILE = 256`.
- Tryby wymagające niedostępnego narzędzia są pomijane z ostrzeżeniem — benchmark nigdy się nie przerywa.
- Bezstratność weryfikowana `np.array_equal`; wynik `lossless_ok=False` jest zapisywany, nie wyrzucany.
- Kolejność kafelków w wideo: sekwencja wg krzywej. Kanały RGB kodowane jako planarne `gbrp` (HEVC) / planarny 4:4:4 (VVC) — bez konwersji koloru, by zachować bezstratność.
- Pliki tymczasowe (klatki, wideo) sprzątane w `try/finally`.

**Odchylenie od spec:** JPEG XL realizujemy przez pakiet `imagecodecs` (Python, pip) zamiast CLI `cjxl`/`djxl`. Powód: brak `cjxl` w systemie i brak pakietu w apt dla Ubuntu 22.04; imagecodecs daje bezstratny JXL bez budowania. `has_tool`-style detekcja zostaje (sprawdzenie importu).

---

## Struktura plików

```
hevc-vvc-lossless-image/
├── photos/                  # istnieje: oryginalne JPG
├── data/                    # tworzone przez generate_images.py
├── results/                 # tworzone przez benchmark.py / report.py
├── utils.py                 # funkcje: tiling, porządki, kodeki, metryki
├── generate_images.py       # krok 1
├── benchmark.py             # krok 2
├── report.py                # krok 3
├── requirements.txt
├── README.md                # tworzony na końcu
└── tests/
    ├── test_tiling.py
    ├── test_orders.py
    └── test_codecs.py       # integracyjne (wymaga ffmpeg)
```

**Kolejność zależności zadań:** Task 1 (setup) → Task 2 (tiling) → Task 3 (porządki) → Task 4 (metryki+detekcja) → Task 5 (HEVC+frame I/O) → Task 6 (JPEG 2000) → Task 7 (JPEG XL) → Task 8 (VVC) → Task 9 (generate_images) → Task 10 (benchmark) → Task 11 (report) → Task 12 (README).

---

### Task 1: Setup — zależności i struktura

**Files:**
- Create: `requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- Produces: działające środowisko z importami `numpy, PIL, hilbertcurve, pandas, matplotlib, imagecodecs, pytest`.

- [ ] **Step 1: Utwórz `requirements.txt`**

```
numpy
pillow
hilbertcurve
pandas
matplotlib
imagecodecs
pytest
```

- [ ] **Step 2: Dodaj wpisy do `.gitignore`**

Dopisz na końcu istniejącego `.gitignore` (jeśli linie już są — pomiń):

```
data/
results/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Zainstaluj zależności**

Run: `pip3 install -r requirements.txt`
Expected: kończy się bez błędu; imagecodecs pobiera wheel binarny.

- [ ] **Step 4: Zweryfikuj importy**

Run:
```bash
python3 -c "import numpy, PIL, hilbertcurve, pandas, matplotlib, imagecodecs, pytest; print('ok')"
```
Expected: wypisuje `ok`.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "Dodaje zaleznosci i wpisy gitignore

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Tiling — pad/split/merge/crop w `utils.py`

**Files:**
- Create: `utils.py`
- Test: `tests/test_tiling.py`

**Interfaces:**
- Produces:
  - `TILE = 256` (stała modułowa)
  - `grid_shape(img_shape: tuple, tile: int) -> tuple[int,int]` → `(rows, cols)`
  - `pad_to_grid(img: np.ndarray, tile: int) -> np.ndarray`
  - `split_tiles(img: np.ndarray, tile: int) -> list[np.ndarray]` (kolejność row-major, kafelki `tile×tile×C`)
  - `merge_tiles(tiles: list[np.ndarray], rows: int, cols: int, tile: int) -> np.ndarray` (obraz z paddingiem)
  - `crop_to_shape(img: np.ndarray, shape: tuple) -> np.ndarray`

- [ ] **Step 1: Napisz failujący test round-trip**

Utwórz `tests/test_tiling.py`:

```python
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils


def test_split_merge_roundtrip_with_padding():
    # 300x400 RGB nie dzieli sie rowno przez 256 -> wymusza padding
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (300, 400, 3), dtype=np.uint8)
    tile = 256
    rows, cols = utils.grid_shape(img.shape, tile)
    tiles = utils.split_tiles(img, tile)
    assert len(tiles) == rows * cols
    assert all(t.shape == (tile, tile, 3) for t in tiles)
    merged = utils.merge_tiles(tiles, rows, cols, tile)
    restored = utils.crop_to_shape(merged, img.shape)
    assert np.array_equal(restored, img)
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `python3 -m pytest tests/test_tiling.py -v`
Expected: FAIL (`AttributeError: module 'utils' has no attribute ...` lub `ModuleNotFoundError`).

- [ ] **Step 3: Zaimplementuj `utils.py`**

Utwórz `utils.py`:

```python
"""Funkcje pomocnicze benchmarku kompresji bezstratnej."""

from __future__ import annotations

import math

import numpy as np


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
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python3 -m pytest tests/test_tiling.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_tiling.py
git commit -m "Dodaje funkcje tilingu obrazu

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Porządki kafelków — raster/Hilbert/Z-order w `utils.py`

**Files:**
- Modify: `utils.py`
- Test: `tests/test_orders.py`

**Interfaces:**
- Consumes: `grid_shape`, `split_tiles`, `merge_tiles` z Task 2.
- Produces:
  - `raster_order(rows, cols) -> list[int]`
  - `hilbert_order(rows, cols) -> list[int]`
  - `zorder_order(rows, cols) -> list[int]`
  - Każdy zwraca permutację indeksów row-major `0..rows*cols-1` (pozycja w sekwencji → indeks row-major).
  - `reorder(items: list, order: list[int]) -> list` → `[items[i] for i in order]`
  - `unreorder(seq: list, order: list[int]) -> list` → odwraca `reorder` (pozycja row-major → element)

- [ ] **Step 1: Napisz failujące testy**

Utwórz `tests/test_orders.py`:

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils
import pytest


@pytest.mark.parametrize("order_fn", [utils.raster_order, utils.hilbert_order, utils.zorder_order])
@pytest.mark.parametrize("rows,cols", [(1, 1), (3, 5), (4, 4), (7, 2), (16, 24)])
def test_order_is_permutation(order_fn, rows, cols):
	order = order_fn(rows, cols)
	assert sorted(order) == list(range(rows * cols))


def test_reorder_unreorder_roundtrip():
	items = list("abcdefghijkl")  # 3x4
	order = utils.hilbert_order(3, 4)
	seq = utils.reorder(items, order)
	restored = utils.unreorder(seq, order)
	assert restored == items
```

- [ ] **Step 2: Uruchom testy — mają failować**

Run: `python3 -m pytest tests/test_orders.py -v`
Expected: FAIL (`AttributeError: module 'utils' has no attribute 'raster_order'`).

- [ ] **Step 3: Dopisz funkcje do `utils.py`**

Dodaj `from hilbertcurve.hilbertcurve import HilbertCurve` do importów (pod `import numpy as np`), a na końcu pliku dopisz:

```python
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
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python3 -m pytest tests/test_orders.py -v`
Expected: PASS (wszystkie warianty).

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_orders.py
git commit -m "Dodaje porzadki kafelkow raster/Hilbert/Z-order

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Metryki i detekcja narzędzi w `utils.py`

**Files:**
- Modify: `utils.py`
- Test: `tests/test_tiling.py` (dopisujemy sekcję metryk — trzyma się prostych funkcji już testowanego pliku)

**Interfaces:**
- Produces:
  - `bits_per_pixel(comp_bytes: int, width: int, height: int) -> float`
  - `compression_ratio(orig_bytes: int, comp_bytes: int) -> float`
  - `verify_lossless(a: np.ndarray, b: np.ndarray) -> bool`
  - `has_tool(name: str) -> bool` (sprawdza `shutil.which`)
  - `has_module(name: str) -> bool` (sprawdza importowalność)

- [ ] **Step 1: Napisz failujące testy**

Dopisz na końcu `tests/test_tiling.py`:

```python
def test_bits_per_pixel():
    # 1000 bajtow, obraz 10x10 -> 8000 bitow / 100 px = 80 bpp
    assert utils.bits_per_pixel(1000, 10, 10) == 80.0


def test_compression_ratio():
    assert utils.compression_ratio(1000, 250) == 4.0


def test_verify_lossless():
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = a.copy()
    assert utils.verify_lossless(a, b) is True
    b[0, 0, 0] = 1
    assert utils.verify_lossless(a, b) is False


def test_has_tool_and_module():
    assert utils.has_tool("python3") is True
    assert utils.has_tool("na_pewno_nie_ma_takiego_narzedzia_xyz") is False
    assert utils.has_module("numpy") is True
    assert utils.has_module("na_pewno_nie_ma_takiego_modulu_xyz") is False
```

- [ ] **Step 2: Uruchom testy — mają failować**

Run: `python3 -m pytest tests/test_tiling.py -v -k "bits or ratio or lossless or has_"`
Expected: FAIL (brak atrybutów).

- [ ] **Step 3: Dopisz funkcje do `utils.py`**

Dodaj do importów na górze: `import importlib.util` i `import shutil`. Na końcu pliku dopisz:

```python
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
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python3 -m pytest tests/test_tiling.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_tiling.py
git commit -m "Dodaje metryki i detekcje narzedzi

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: HEVC — frame I/O i wywołania ffmpeg w `utils.py`

**Files:**
- Modify: `utils.py`
- Test: `tests/test_codecs.py`

**Interfaces:**
- Consumes: nic nowego.
- Produces:
  - `write_frames(tiles: list[np.ndarray], frames_dir: str) -> None` (zapisuje `frame_00000.png`, …)
  - `read_frames(frames_dir: str, n: int) -> list[np.ndarray]`
  - `encode_hevc(frames_dir: str, out_path: str, inter: bool) -> None`
  - `decode_hevc(video_path: str, frames_dir: str) -> None`
  - Kodowanie używa `-pix_fmt gbrp -x265-params lossless=1[:keyint=1]`; `inter=False` wymusza `keyint=1` (all-intra).

- [ ] **Step 1: Napisz failujący test integracyjny**

Utwórz `tests/test_codecs.py`:

```python
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import utils
import pytest


def _small_rgb(seed=0, h=300, w=400):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


@pytest.mark.skipif(not utils.has_tool("ffmpeg"), reason="brak ffmpeg")
@pytest.mark.parametrize("inter", [True, False])
def test_hevc_frames_lossless_roundtrip(inter):
    img = _small_rgb()
    tile = 256
    rows, cols = utils.grid_shape(img.shape, tile)
    tiles = utils.split_tiles(img, tile)
    with tempfile.TemporaryDirectory() as d:
        fin = os.path.join(d, "in"); os.makedirs(fin)
        fout = os.path.join(d, "out"); os.makedirs(fout)
        video = os.path.join(d, "v.mkv")
        utils.write_frames(tiles, fin)
        utils.encode_hevc(fin, video, inter=inter)
        assert os.path.getsize(video) > 0
        utils.decode_hevc(video, fout)
        back_tiles = utils.read_frames(fout, len(tiles))
        merged = utils.merge_tiles(back_tiles, rows, cols, tile)
        restored = utils.crop_to_shape(merged, img.shape)
        assert utils.verify_lossless(img, restored)
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `python3 -m pytest tests/test_codecs.py -v -k hevc`
Expected: FAIL (brak `utils.write_frames`).

- [ ] **Step 3: Dopisz funkcje do `utils.py`**

Dodaj do importów: `import os`, `import subprocess`, oraz `from PIL import Image`. Na końcu pliku dopisz:

```python
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
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python3 -m pytest tests/test_codecs.py -v -k hevc`
Expected: PASS dla `inter=True` i `inter=False`.

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_codecs.py
git commit -m "Dodaje kodek HEVC i wejscie/wyjscie klatek

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: JPEG 2000 w `utils.py`

**Files:**
- Modify: `utils.py`
- Test: `tests/test_codecs.py`

**Interfaces:**
- Produces:
  - `encode_jpeg2000(img: np.ndarray, out_path: str) -> None` (bezstratny, `irreversible=False`)
  - `decode_jpeg2000(path: str) -> np.ndarray`

- [ ] **Step 1: Napisz failujący test**

Dopisz do `tests/test_codecs.py`:

```python
def test_jpeg2000_lossless_roundtrip():
    img = _small_rgb(seed=2, h=128, w=160)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jp2")
        utils.encode_jpeg2000(img, p)
        assert os.path.getsize(p) > 0
        back = utils.decode_jpeg2000(p)
        assert utils.verify_lossless(img, back)
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `python3 -m pytest tests/test_codecs.py -v -k jpeg2000`
Expected: FAIL (brak funkcji).

- [ ] **Step 3: Dopisz funkcje do `utils.py`**

Na końcu pliku dopisz:

```python
def encode_jpeg2000(img: np.ndarray, out_path: str) -> None:
	"""Zapisuje obraz bezstratnie jako JPEG 2000 (odwracalna falka 5/3)."""

	Image.fromarray(img).save(out_path, format="JPEG2000", irreversible=False)


def decode_jpeg2000(path: str) -> np.ndarray:
	"""Wczytuje obraz JPEG 2000 jako tablice NumPy."""

	return np.asarray(Image.open(path))
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python3 -m pytest tests/test_codecs.py -v -k jpeg2000`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_codecs.py
git commit -m "Dodaje kodek JPEG 2000

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: JPEG XL przez imagecodecs w `utils.py`

**Files:**
- Modify: `utils.py`
- Test: `tests/test_codecs.py`

**Interfaces:**
- Produces:
  - `encode_jpegxl(img: np.ndarray, out_path: str) -> None` (bezstratny)
  - `decode_jpegxl(path: str) -> np.ndarray`
  - Dostępność wykrywana przez `has_module("imagecodecs")`.

- [ ] **Step 1: Napisz failujący test**

Dopisz do `tests/test_codecs.py`:

```python
@pytest.mark.skipif(not utils.has_module("imagecodecs"), reason="brak imagecodecs")
def test_jpegxl_lossless_roundtrip():
    img = _small_rgb(seed=3, h=128, w=160)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jxl")
        utils.encode_jpegxl(img, p)
        assert os.path.getsize(p) > 0
        back = utils.decode_jpegxl(p)
        assert utils.verify_lossless(img, back)
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `python3 -m pytest tests/test_codecs.py -v -k jpegxl`
Expected: FAIL (brak funkcji).

- [ ] **Step 3: Dopisz funkcje do `utils.py`**

Na końcu pliku dopisz (import lokalny, by moduł ładował się nawet bez imagecodecs):

```python
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
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python3 -m pytest tests/test_codecs.py -v -k jpegxl`
Expected: PASS. Jeśli `jpegxl_encode` nie akceptuje `lossless=True` w zainstalowanej wersji, użyj `distance=0` zamiast `lossless=True` (oba oznaczają tryb bezstratny) i uruchom ponownie.

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_codecs.py
git commit -m "Dodaje kodek JPEG XL przez imagecodecs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: VVC — budowa VTM i wrapper w `utils.py`

**Files:**
- Modify: `utils.py`
- Test: `tests/test_codecs.py`

**Interfaces:**
- Produces:
  - `encode_vvc(frames_dir: str, out_path: str, width: int, height: int, n_frames: int, inter: bool) -> None`
  - `decode_vvc(bitstream: str, frames_dir: str, width: int, height: int) -> None`
  - Dostępność: `has_tool("EncoderAppStatic") and has_tool("DecoderAppStatic")`.
  - RGB pakowane jako planarny YUV444 8-bit (kanały R,G,B → 3 płaszczyzny) w surowym `.yuv`; brak konwersji koloru → bezstratność. Klatki łączone w jeden strumień YUV w kolejności sekwencji.

**Kontekst — dlaczego VTM, nie vvenc:** Wcześniejsza próba użyła `vvenc` (zoptymalizowanego enkodera Fraunhofera). Ustalono empirycznie i w źródłach (`EncCu.cpp`: `const bool lossless = false;`), że vvenc **nie** obsługuje prawdziwie bezstratnego kodowania (flaga `--CostMode lossless` zmienia tylko funkcję kosztu RD → błędy ±1 LSB) ani wejścia YUV444. Dlatego używamy **VTM** (VVC Test Model — oprogramowanie referencyjne JVET, licencja BSD-3-Clause-Clear), które wspiera transquant bypass (prawdziwy lossless) i YUV444. VTM jest znacznie wolniejszy — akceptowalne dla benchmarku offline.

**Uwaga:** dokładne flagi trybu bezstratnego VTM potwierdź przez `--help`/dokumentację (Step 2). Integracyjny test lossless jest ostatecznym wyrocznikiem poprawności. Jeśli w `~/tools` zostały artefakty vvenc/vvdec z poprzedniej próby, można je zignorować lub usunąć — nie są używane.

- [ ] **Step 1: Zbuduj VTM**

Run:
```bash
mkdir -p ~/tools && cd ~/tools
git clone --depth 1 https://vcgit.hhi.fraunhofer.de/jvet/VVCSoftware_VTM.git vtm
cd vtm && mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)
```
Expected: powstają binaria `EncoderAppStatic` i `DecoderAppStatic` (znajdź: `find ~/tools/vtm -name 'EncoderAppStatic' -o -name 'DecoderAppStatic'`; zwykle w `~/tools/vtm/bin/`). Pliki konfiguracyjne enkodera są w `~/tools/vtm/cfg/` (m.in. `encoder_intra_vtm.cfg`, `encoder_lowdelay_vtm.cfg`).

- [ ] **Step 2: Dodaj binaria do PATH i potwierdź opcje lossless**

Run:
```bash
export PATH="$(dirname $(find ~/tools/vtm -name EncoderAppStatic | head -1)):$PATH"
EncoderAppStatic --help 2>&1 | grep -iE "CostMode|Lossless|TransquantBypass|InputChromaFormat|InputBitDepth|SourceWidth|SourceHeight|FramesToBeEncoded|IntraPeriod"
ls ~/tools/vtm/cfg/ | grep -iE "intra|lowdelay|randomaccess"
```
Expected: potwierdź nazwy opcji: `--SourceWidth`/`--SourceHeight`, `--InputChromaFormat=444`, `--InputBitDepth=8`, tryb bezstratny (spodziewane `--CostMode=lossless`, ewentualnie `--TransquantBypassEnable=1`). Zanotuj dokładne flagi i ścieżki cfg — wstaw je w Step 4. Dodaj eksport PATH do `~/.bashrc`, by narzędzia były trwale widoczne (uwzględnij katalog cfg jeśli wrapper go potrzebuje — patrz `kVtmCfgDir` niżej).

- [ ] **Step 3: Napisz failujący test integracyjny**

Dopisz do `tests/test_codecs.py`:

```python
_VVC = utils.has_tool("EncoderAppStatic") and utils.has_tool("DecoderAppStatic")


@pytest.mark.skipif(not _VVC, reason="brak VTM (EncoderAppStatic/DecoderAppStatic)")
@pytest.mark.parametrize("inter", [True, False])
def test_vvc_lossless_roundtrip(inter):
    img = _small_rgb(seed=4)
    tile = 256
    rows, cols = utils.grid_shape(img.shape, tile)
    tiles = utils.split_tiles(img, tile)
    with tempfile.TemporaryDirectory() as d:
        fin = os.path.join(d, "in"); os.makedirs(fin)
        fout = os.path.join(d, "out"); os.makedirs(fout)
        utils.write_frames(tiles, fin)
        bitstream = os.path.join(d, "v.vvc")
        utils.encode_vvc(fin, bitstream, tile, tile, len(tiles), inter=inter)
        assert os.path.getsize(bitstream) > 0
        utils.decode_vvc(bitstream, fout, tile, tile)
        back_tiles = utils.read_frames(fout, len(tiles))
        merged = utils.merge_tiles(back_tiles, rows, cols, tile)
        restored = utils.crop_to_shape(merged, img.shape)
        assert utils.verify_lossless(img, restored)
```

- [ ] **Step 4: Uruchom test — ma failować, potem zaimplementuj wrapper**

Run: `python3 -m pytest tests/test_codecs.py -v -k vvc`
Expected: FAIL (brak `utils.encode_vvc`).

Dopisz do `utils.py`. VTM wspiera YUV444, więc pakujemy 3 kanały RGB w jeden strumień YUV444 (helpery `_frames_to_yuv444`/`_yuv444_to_frames`). Ustaw `kVtmCfgDir` na katalog cfg VTM (znaleziony w Step 1) i podstaw dokładne flagi lossless potwierdzone w Step 2 w miejscu `# LOSSLESS FLAGS`:

```python
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
	"""Koduje sekwencje klatek bezstratnie kodekiem VVC (VTM) na planarnym YUV444."""

	yuv = out_path + ".in.yuv"
	cfg = os.path.join(kVtmCfgDir, "encoder_lowdelay_vtm.cfg" if inter else "encoder_intra_vtm.cfg")
	try:
		_frames_to_yuv444(frames_dir, n_frames, yuv)
		# LOSSLESS FLAGS: potwierdzone w Step 2 (spodziewane: --CostMode=lossless)
		_run([
			"EncoderAppStatic", "-c", cfg,
			"-i", yuv, "-b", out_path, "-o", "/dev/null",
			f"--SourceWidth={width}", f"--SourceHeight={height}",
			"--InputChromaFormat=444", "--InputBitDepth=8",
			"--FrameRate=1", f"--FramesToBeEncoded={n_frames}",
			"--CostMode=lossless",
		])
	finally:
		if os.path.exists(yuv):
			os.remove(yuv)


def decode_vvc(bitstream: str, frames_dir: str, width: int, height: int) -> None:
	"""Dekoduje strumien VVC (VTM) do klatek PNG."""

	yuv = bitstream + ".out.yuv"
	try:
		_run(["DecoderAppStatic", "-b", bitstream, "-o", yuv])
		_yuv444_to_frames(yuv, frames_dir, width, height)
	finally:
		if os.path.exists(yuv):
			os.remove(yuv)
```

- [ ] **Step 5: Uruchom test — dostrój flagi aż przejdzie**

Run: `python3 -m pytest tests/test_codecs.py -v -k vvc`
Expected: PASS (bit-exact) dla `inter=True` i `inter=False`. Jeśli lossless nie przechodzi, popraw `# LOSSLESS FLAGS` (np. dodaj `--TransquantBypassEnable=1 --CUTransquantBypassFlagForce=1`) oraz argumenty (cfg, chroma, bitdepth) wg `--help` z Step 2, aż round-trip będzie bit-exact. VTM ma pełny tryb bezstratny, więc lossless jest osiągalny — w razie uporczywych problemów zgłoś jako BLOCKED z dokładnym opisem prób.

- [ ] **Step 6: Commit**

```bash
git add utils.py tests/test_codecs.py
git commit -m "Dodaje kodek VVC (VTM) na planarnym YUV444

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: `generate_images.py` — obrazy naturalne i syntetyczne

**Files:**
- Create: `generate_images.py`

**Interfaces:**
- Consumes: nic z utils (samodzielny skrypt korzystający z PIL/numpy).
- Produces: pliki `data/nature_*.png` i `data/synth_*.png`. Idempotentny (pomija istniejące).

- [ ] **Step 1: Utwórz `generate_images.py`**

```python
"""Krok 1: przygotowuje obrazy wejsciowe (naturalne + syntetyczne) w data/."""

from __future__ import annotations

import os

import numpy as np
from PIL import Image


kPhotosDir = "photos"
kDataDir = "data"
kNaturalPhotos = ["P1066097", "P1066103", "P1066124"]  # 3 zdjecia naturalne
kSynthSize = 5000  # bok obrazow syntetycznych (px)


def _save(name: str, img: np.ndarray) -> None:
	path = os.path.join(kDataDir, name)
	if os.path.exists(path):
		print(f"Pomijam istniejacy: {path}")
		return
	Image.fromarray(img).save(path)
	print(f"Zapisano: {path} {img.shape}")


def _decode_natural() -> None:
	for stem in kNaturalPhotos:
		src = os.path.join(kPhotosDir, f"{stem}.jpg")
		if not os.path.exists(src):
			print(f"Brak zrodla, pomijam: {src}")
			continue
		img = np.asarray(Image.open(src).convert("RGB"))
		_save(f"nature_{stem}.png", img)


def _gen_gradient() -> np.ndarray:
	n = kSynthSize
	x = np.linspace(0, 255, n, dtype=np.uint8)
	row = np.tile(x, (n, 1))
	return np.stack([row, row.T, ((row.astype(int) + row.T.astype(int)) // 2).astype(np.uint8)], axis=2)


def _gen_noise() -> np.ndarray:
	rng = np.random.default_rng(42)
	return rng.integers(0, 256, (kSynthSize, kSynthSize, 3), dtype=np.uint8)


def _gen_checkerboard() -> np.ndarray:
	n = kSynthSize
	block = 32
	idx = (np.arange(n) // block) % 2
	pattern = (idx[:, None] ^ idx[None, :]).astype(np.uint8) * 255
	return np.stack([pattern, pattern, pattern], axis=2)


def _gen_repeated() -> np.ndarray:
	# Powtarzajacy sie motyw (symuluje wielokrotnie wystepujace obiekty, np. krwinki)
	rng = np.random.default_rng(7)
	motif = rng.integers(0, 256, (50, 50, 3), dtype=np.uint8)
	reps = kSynthSize // 50 + 1
	tiled = np.tile(motif, (reps, reps, 1))
	return tiled[:kSynthSize, :kSynthSize]


def main() -> None:
	os.makedirs(kDataDir, exist_ok=True)
	_decode_natural()
	_save("synth_gradient.png", _gen_gradient())
	_save("synth_noise.png", _gen_noise())
	_save("synth_checkerboard.png", _gen_checkerboard())
	_save("synth_repeated.png", _gen_repeated())
	print("Gotowe.")


if __name__ == "__main__":
	main()
```

- [ ] **Step 2: Uruchom skrypt**

Run: `python3 generate_images.py`
Expected: powstaje `data/` z 3 plikami `nature_*.png` i 4 `synth_*.png`; ponowne uruchomienie wypisuje "Pomijam istniejacy".

- [ ] **Step 3: Zweryfikuj wyniki**

Run:
```bash
python3 -c "
import os, numpy as np
from PIL import Image
for f in sorted(os.listdir('data')):
    im = np.asarray(Image.open('data/'+f))
    print(f, im.shape, im.dtype)
"
```
Expected: wszystkie pliki RGB uint8; `nature_*` ~4000×6000, `synth_*` 5000×5000×3.

- [ ] **Step 4: Commit**

```bash
git add generate_images.py
git commit -m "Dodaje generator obrazow naturalnych i syntetycznych

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 10: `benchmark.py` — macierz eksperymentów → CSV

**Files:**
- Create: `benchmark.py`

**Interfaces:**
- Consumes: cały `utils.py` (tiling, porządki, kodeki, metryki, detekcja).
- Produces: `results/results.csv` z kolumnami: `image, image_type, codec_mode, tile_size, n_tiles, orig_bytes, comp_bytes, bpp, ratio, encode_s, decode_s, lossless_ok`.

- [ ] **Step 1: Utwórz `benchmark.py`**

```python
"""Krok 2: uruchamia macierz eksperymentow kompresji bezstratnej -> results/results.csv."""

from __future__ import annotations

import csv
import os
import tempfile
import time

import numpy as np
from PIL import Image

import utils


kDataDir = "data"
kResultsDir = "results"
kCsvPath = os.path.join(kResultsDir, "results.csv")

# codec: hevc|vvc|jpeg2000|jpegxl ; tiled: bool ; curve: raster|hilbert|zorder|None ; inter: bool
EXPERIMENTS = {
	"hevc_full":    dict(codec="hevc", tiled=False, curve=None, inter=False),
	"hevc_intra":   dict(codec="hevc", tiled=True, curve="raster", inter=False),
	"hevc_raster":  dict(codec="hevc", tiled=True, curve="raster", inter=True),
	"hevc_hilbert": dict(codec="hevc", tiled=True, curve="hilbert", inter=True),
	"hevc_zorder":  dict(codec="hevc", tiled=True, curve="zorder", inter=True),
	"vvc_full":     dict(codec="vvc", tiled=False, curve=None, inter=False),
	"vvc_hilbert":  dict(codec="vvc", tiled=True, curve="hilbert", inter=True),
	"jpeg2000":     dict(codec="jpeg2000", tiled=False, curve=None, inter=False),
	"jpegxl":       dict(codec="jpegxl", tiled=False, curve=None, inter=False),
}

kCsvFields = [
	"image", "image_type", "codec_mode", "tile_size", "n_tiles",
	"orig_bytes", "comp_bytes", "bpp", "ratio", "encode_s", "decode_s", "lossless_ok",
]


def _mode_available(cfg: dict) -> bool:
	codec = cfg["codec"]
	if codec == "hevc":
		return utils.has_tool("ffmpeg")
	if codec == "vvc":
		return utils.has_tool("EncoderAppStatic") and utils.has_tool("DecoderAppStatic")
	if codec == "jpeg2000":
		return True  # Pillow + libopenjpeg
	if codec == "jpegxl":
		return utils.has_module("imagecodecs")
	return False


def _run_video_mode(img, cfg, workdir):
	"""Kodowanie/dekodowanie trybow kafelkowych i pelnoklatkowych HEVC/VVC."""

	tile = utils.TILE
	if cfg["tiled"]:
		rows, cols = utils.grid_shape(img.shape, tile)
		tiles = utils.split_tiles(img, tile)
		order = utils.ORDERS[cfg["curve"]](rows, cols)
		frames = utils.reorder(tiles, order)
		frame_w = frame_h = tile
		n_tiles = len(tiles)
	else:
		# Caly obraz jako jedna klatka (dopelniony do parzystych wymiarow nie jest wymagany dla gbrp)
		frames = [img]
		rows = cols = None
		frame_h, frame_w = img.shape[0], img.shape[1]
		n_tiles = 0

	fin = os.path.join(workdir, "in"); os.makedirs(fin)
	fout = os.path.join(workdir, "out"); os.makedirs(fout)
	utils.write_frames(frames, fin)

	if cfg["codec"] == "hevc":
		video = os.path.join(workdir, "v.mkv")
		t0 = time.perf_counter(); utils.encode_hevc(fin, video, inter=cfg["inter"]); enc = time.perf_counter() - t0
		comp_bytes = os.path.getsize(video)
		t0 = time.perf_counter(); utils.decode_hevc(video, fout); dec = time.perf_counter() - t0
	else:  # vvc
		bitstream = os.path.join(workdir, "v.vvc")
		t0 = time.perf_counter()
		utils.encode_vvc(fin, bitstream, frame_w, frame_h, len(frames), inter=cfg["inter"])
		enc = time.perf_counter() - t0
		comp_bytes = os.path.getsize(bitstream)
		t0 = time.perf_counter(); utils.decode_vvc(bitstream, fout, frame_w, frame_h); dec = time.perf_counter() - t0

	back = utils.read_frames(fout, len(frames))
	if cfg["tiled"]:
		restored_tiles = utils.unreorder(back, order)
		merged = utils.merge_tiles(restored_tiles, rows, cols, tile)
		restored = utils.crop_to_shape(merged, img.shape)
	else:
		restored = back[0]
	return comp_bytes, enc, dec, restored, tile if cfg["tiled"] else 0, n_tiles


def _run_image_mode(img, cfg, workdir):
	"""Kodowanie/dekodowanie JPEG 2000 / JPEG XL (caly obraz)."""

	if cfg["codec"] == "jpeg2000":
		path = os.path.join(workdir, "a.jp2")
		t0 = time.perf_counter(); utils.encode_jpeg2000(img, path); enc = time.perf_counter() - t0
		comp_bytes = os.path.getsize(path)
		t0 = time.perf_counter(); restored = utils.decode_jpeg2000(path); dec = time.perf_counter() - t0
	else:  # jpegxl
		path = os.path.join(workdir, "a.jxl")
		t0 = time.perf_counter(); utils.encode_jpegxl(img, path); enc = time.perf_counter() - t0
		comp_bytes = os.path.getsize(path)
		t0 = time.perf_counter(); restored = utils.decode_jpegxl(path); dec = time.perf_counter() - t0
	return comp_bytes, enc, dec, restored, 0, 0


def _run_one(img, mode, cfg, workdir):
	if cfg["codec"] in ("hevc", "vvc"):
		return _run_video_mode(img, cfg, workdir)
	return _run_image_mode(img, cfg, workdir)


def main() -> None:
	os.makedirs(kResultsDir, exist_ok=True)
	images = sorted(f for f in os.listdir(kDataDir) if f.endswith(".png"))
	if not images:
		print("Brak obrazow w data/. Uruchom najpierw generate_images.py.")
		return

	available = {m: c for m, c in EXPERIMENTS.items() if _mode_available(c)}
	for m in EXPERIMENTS:
		if m not in available:
			print(f"OSTRZEZENIE: tryb '{m}' pominiety (brak narzedzia).")

	with open(kCsvPath, "w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=kCsvFields)
		writer.writeheader()
		for image in images:
			img = np.asarray(Image.open(os.path.join(kDataDir, image)).convert("RGB"))
			h, w = img.shape[0], img.shape[1]
			orig_bytes = w * h * 3
			image_type = "nature" if image.startswith("nature") else "synth"
			for mode, cfg in available.items():
				with tempfile.TemporaryDirectory() as workdir:
					try:
						comp, enc, dec, restored, tsize, n_tiles = _run_one(img, mode, cfg, workdir)
					except Exception as error:  # noqa: BLE001
						print(f"BLAD {image}/{mode}: {error}")
						continue
					ok = utils.verify_lossless(img, restored)
					if not ok:
						print(f"OSTRZEZENIE: {image}/{mode} nie jest bezstratny!")
					writer.writerow({
						"image": image, "image_type": image_type, "codec_mode": mode,
						"tile_size": tsize, "n_tiles": n_tiles, "orig_bytes": orig_bytes,
						"comp_bytes": comp, "bpp": round(utils.bits_per_pixel(comp, w, h), 4),
						"ratio": round(utils.compression_ratio(orig_bytes, comp), 4),
						"encode_s": round(enc, 3), "decode_s": round(dec, 3), "lossless_ok": ok,
					})
					handle.flush()
					print(f"OK {image}/{mode}: bpp={utils.bits_per_pixel(comp, w, h):.3f} lossless={ok}")
	print(f"Zapisano wyniki: {kCsvPath}")


if __name__ == "__main__":
	main()
```

- [ ] **Step 2: Test dymny na małym zestawie**

Run:
```bash
mkdir -p /tmp/smoke_data && python3 -c "
import numpy as np
from PIL import Image
rng = np.random.default_rng(0)
Image.fromarray(rng.integers(0,256,(300,400,3),dtype=np.uint8)).save('/tmp/smoke_data/synth_x.png')
"
# Podmien katalog danych na czas testu
python3 -c "
import benchmark, os
benchmark.kDataDir='/tmp/smoke_data'; benchmark.kResultsDir='/tmp/smoke_res'
benchmark.kCsvPath=os.path.join('/tmp/smoke_res','results.csv')
benchmark.main()
"
cat /tmp/smoke_res/results.csv
```
Expected: CSV z wierszami dla dostępnych trybów (co najmniej hevc_* i jpeg2000), wszystkie `lossless_ok=True`. Tryby bez narzędzi wypisane jako pominięte.

- [ ] **Step 3: Commit**

```bash
git add benchmark.py
git commit -m "Dodaje glowna petle benchmarku

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 11: `report.py` — wykresy z CSV

**Files:**
- Create: `report.py`

**Interfaces:**
- Consumes: `results/results.csv`.
- Produces: `results/bpp_by_codec.png`, `results/ratio_by_mode.png`.

- [ ] **Step 1: Utwórz `report.py`**

```python
"""Krok 3: generuje wykresy podsumowujace z results/results.csv."""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


kResultsDir = "results"
kCsvPath = os.path.join(kResultsDir, "results.csv")


def _plot_bpp_by_codec(df: pd.DataFrame) -> None:
	pivot = df.pivot_table(index="image", columns="codec_mode", values="bpp")
	ax = pivot.plot(kind="bar", figsize=(14, 7))
	ax.set_ylabel("bity na piksel (BPP)")
	ax.set_title("BPP wg obrazu i trybu kompresji (mniej = lepiej)")
	ax.legend(title="codec_mode", bbox_to_anchor=(1.01, 1), loc="upper left")
	plt.tight_layout()
	out = os.path.join(kResultsDir, "bpp_by_codec.png")
	plt.savefig(out, dpi=120)
	plt.close()
	print(f"Zapisano: {out}")


def _plot_ratio_by_mode(df: pd.DataFrame) -> None:
	means = df.groupby("codec_mode")["ratio"].mean().sort_values(ascending=False)
	ax = means.plot(kind="bar", figsize=(12, 6), color="steelblue")
	ax.set_ylabel("sredni wspolczynnik kompresji")
	ax.set_title("Sredni wspolczynnik kompresji wg trybu (wiecej = lepiej)")
	plt.tight_layout()
	out = os.path.join(kResultsDir, "ratio_by_mode.png")
	plt.savefig(out, dpi=120)
	plt.close()
	print(f"Zapisano: {out}")


def main() -> None:
	if not os.path.exists(kCsvPath):
		print(f"Brak {kCsvPath}. Uruchom najpierw benchmark.py.")
		return
	df = pd.read_csv(kCsvPath)
	if df.empty:
		print("CSV jest pusty — brak danych do wykresow.")
		return
	_plot_bpp_by_codec(df)
	_plot_ratio_by_mode(df)
	print("Gotowe.")


if __name__ == "__main__":
	main()
```

- [ ] **Step 2: Test na przykładowym CSV**

Run:
```bash
mkdir -p /tmp/rep && python3 -c "
import pandas as pd, os
os.makedirs('/tmp/rep', exist_ok=True)
pd.DataFrame([
 dict(image='synth_x.png', image_type='synth', codec_mode='hevc_full', bpp=8.1, ratio=2.9),
 dict(image='synth_x.png', image_type='synth', codec_mode='hevc_hilbert', bpp=8.4, ratio=2.8),
 dict(image='synth_x.png', image_type='synth', codec_mode='jpeg2000', bpp=9.0, ratio=2.6),
]).to_csv('/tmp/rep/results.csv', index=False)
"
python3 -c "
import report
report.kResultsDir='/tmp/rep'
import os; report.kCsvPath=os.path.join('/tmp/rep','results.csv')
report.main()
"
ls -la /tmp/rep/*.png
```
Expected: powstają `bpp_by_codec.png` i `ratio_by_mode.png`.

- [ ] **Step 3: Commit**

```bash
git add report.py
git commit -m "Dodaje generowanie wykresow

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 12: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Utwórz `README.md`**

```markdown
# hevc-vvc-lossless-image

Benchmark bezstratnej kompresji dużych obrazów kodekami wideo (HEVC, VVC) w różnych
trybach kafelkowania (raster / krzywa Hilberta / Z-order), porównany z JPEG 2000 i JPEG XL.

Opis tematu i architektura: patrz [CLAUDE.md](CLAUDE.md) oraz
[docs/superpowers/specs/2026-07-15-lossless-video-codec-benchmark-design.md](docs/superpowers/specs/2026-07-15-lossless-video-codec-benchmark-design.md).

## Wymagania

- Python 3.10+
- ffmpeg z libx265 i libopenjpeg (w PATH)
- Opcjonalnie: VTM (EncoderAppStatic/DecoderAppStatic) dla VVC, zbudowane ze źródeł
- Zależności Pythona: `pip install -r requirements.txt`

## Uruchomienie

```bash
pip install -r requirements.txt
python generate_images.py   # krok 1: przygotuj obrazy w data/
python benchmark.py         # krok 2: wykonaj eksperymenty -> results/results.csv
python report.py            # krok 3: wykresy -> results/*.png
```

## Testy

```bash
python -m pytest -v
```

Testy kodeków wymagają ffmpeg; testy VVC są pomijane, gdy brak VTM (EncoderAppStatic/DecoderAppStatic).

## Tryby eksperymentów

`hevc_full`, `hevc_intra`, `hevc_raster`, `hevc_hilbert`, `hevc_zorder`,
`vvc_full`, `vvc_hilbert`, `jpeg2000`, `jpegxl`. Rozmiar kafelka: 256×256.
Tryby wymagające niedostępnych narzędzi są automatycznie pomijane.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Dodaje README z instrukcja uruchomienia

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Uwagi końcowe dla wykonawcy

- **Uruchamianie pełnego benchmarku** na obrazach ~5000×5000 może trwać kilka–kilkanaście minut (szczególnie HEVC inter na setkach kafelków i `synth_noise`). To normalne. Test dymny (Task 10 Step 2) na małym obrazie potwierdza poprawność bez czekania.
- **Kolejność krytyczna:** merge/unreorder muszą być spójne z reorder/split — Task 10 używa `unreorder(back, order)` i `merge_tiles`. Jeśli obraz po dekodowaniu jest "poprzestawiany", błąd jest tutaj.
- **Bezstratność full-image:** dla HEVC full obraz o nieparzystych wymiarach kodowany jako `gbrp` nie wymaga paddingu (brak subsamplingu chroma). Gdyby ffmpeg protestował na wymiary, dopełnij do parzystych i przytnij po dekodowaniu.
