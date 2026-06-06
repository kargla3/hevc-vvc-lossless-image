# Plan: Architektura systemu benchmarkingu kompresji bezstratnej

System porównuje HEVC, VVC, JPEG 2000 i JPEG XL w bezstratnej kompresji obrazów statycznych,
z nowatorską techniką porządkowania kafelków krzywą Hilberta traktowanych jako klatki wideo
(eksploatacja predykcji międzyklatkowej).

---

## Funkcjonalności programu

| # | Moduł | Opis |
|---|---|---|
| F1 | **Image I/O** | Wczytywanie obrazów PNG/TIFF/BMP, obsługa dużych plików (streaming), weryfikacja pixel-perfect po dekompresji |
| F2 | **Tiling** | Podział obrazu na kafelki siatką prostokątną; obsługa brzegów (padding); generowanie różnych porządków: raster, Z-order, Hilbert |
| F3 | **Hilbert Ordering** | Mapowanie kafelków na krzywą Hilberta 2D (`hilbertcurve`); parametryzacja iteracji `p`; rekonstrukcja odwrotna |
| F4 | **Video Assembly** | Składanie kafelków w sekwencję klatek PNG → pipeline do enkodera wideo; wypakowywanie klatek z wideo |
| F5 | **Kodery HEVC/VVC** | Wywołania `ffmpeg` z `libx265`/`libvvenc`; tryby: (a) obraz całościowo jako 1 klatka, (b) kafelki intra-only, (c) kafelki Hilbert inter-frame |
| F6 | **Kodery JPEG 2000/XL** | Wywołania przez `glymur`/`imagecodecs` i `cjxl`; parametryzacja wysiłku (`effort`) |
| F7 | **Metryki** | BPP, współczynnik kompresji, rozmiar pliku, czas kodowania i dekodowania, weryfikacja lossless |
| F8 | **Pipeline** | Orkiestracja: obraz → tiling → kodowanie → dekodowanie → weryfikacja → zapis metryk |
| F9 | **BenchmarkRunner** | Uruchamianie macierzy eksperymentów: wiele obrazów × wiele konfiguracji kodeków × wiele rozmiarów kafelków |
| F10 | **Reporting** | Eksport wyników do CSV/JSON, wykresy matplotlib (BD-rate curves, bar charts BPP) |
| F11 | **CLI** | `python -m lossless_bench run --config config.yaml` |

---

## Struktura projektu

```
hevc-vvc-lossless-image/
├── README.md
├── requirements.txt                # wszystkie zależności projektu
├── .venv/                          # środowisko wirtualne
│
├── data/
│   ├── input/                      # testowe obrazy PNG
│   └── output/                     # pliki skompresowane per kodek/konfiguracja
│
├── src/
│   └── lossless_bench/
│       ├── __init__.py
│       ├── config.py               # dataclassy konfiguracji (pydantic)
│       ├── pipeline.py             # CompressionPipeline
│       ├── runner.py               # BenchmarkRunner
│       │
│       ├── image/
│       │   ├── loader.py           # ImageLoader
│       │   └── saver.py            # ImageSaver
│       │
│       ├── tiling/
│       │   ├── base.py             # Tiler (ABC)
│       │   ├── raster.py           # RasterTiler
│       │   ├── hilbert.py          # HilbertTiler
│       │   ├── z_order.py          # ZOrderTiler
│       │   └── assembler.py        # VideoAssembler
│       │
│       ├── encoders/
│       │   ├── base.py             # Encoder (ABC)
│       │   ├── hevc.py             # HEVCEncoder
│       │   ├── vvc.py              # VVCEncoder
│       │   ├── jpeg2000.py         # JPEG2000Encoder
│       │   └── jpegxl.py          # JPEGXLEncoder
│       │
│       └── metrics/
│           ├── compression.py      # CompressionMetrics, MetricsCalculator
│           └── report.py           # ResultsExporter
│
├── scripts/
│   ├── run_benchmark.py            # CLI entry point
│   └── generate_report.py
│
├── tests/
│   ├── conftest.py
│   ├── test_tiling.py
│   ├── test_encoders.py
│   └── test_metrics.py
│
├── notebooks/
│   └── analysis.ipynb
│
└── results/
    ├── raw/                        # JSON/CSV per eksperyment
    └── figures/                    # wykresy
```

---

## Środowisko wirtualne

Projekt używa standardowego środowiska wirtualnego Python (`venv`) umieszczonego w katalogu `.venv/`.

### Pierwsze uruchomienie (setup)

```bash
# 1. Utwórz środowisko wirtualne
python -m venv .venv

# 2. Aktywuj (Windows PowerShell)
.venv\Scripts\Activate.ps1

# 2. Aktywuj (Windows cmd)
.venv\Scripts\activate.bat

# 2. Aktywuj (Linux / macOS)
source .venv/bin/activate

# 3. Zainstaluj zależności
pip install -r requirements.txt
```

### Zależności (`requirements.txt`)

```txt
pillow
numpy
hilbertcurve
glymur
imagecodecs
pandas
matplotlib
seaborn
pydantic
tqdm
click

pytest
ruff
black
```

### Codzienna praca

```bash
# Aktywuj środowisko przed pracą
.venv\Scripts\Activate.ps1      # Windows
source .venv/bin/activate        # Linux/macOS

# Uruchom benchmark
python -m lossless_bench run --config config.yaml

# Uruchom testy
pytest tests/

# Deaktywuj po skończeniu
deactivate
```

---

## Diagram klas

```
┌─────────────────────────────┐
│      «dataclass»            │
│      EncoderConfig          │
├─────────────────────────────┤
│ + codec: str                │
│ + mode: EncodingMode        │  ← enum: INTRA / INTER / FULL_IMAGE
│ + preset: str               │
│ + extra_params: dict        │
└─────────────────────────────┘

┌─────────────────────────────┐
│      «dataclass»            │
│      TilingConfig           │
├─────────────────────────────┤
│ + tile_width: int           │
│ + tile_height: int          │
│ + curve: CurveType          │  ← enum: RASTER / HILBERT / Z_ORDER
│ + padding_mode: str         │
└─────────────────────────────┘

┌─────────────────────────────┐
│      «dataclass»            │
│      BenchmarkConfig        │
├─────────────────────────────┤
│ + image_paths: list[Path]   │
│ + encoder_configs: list[EC] │
│ + tiling_configs: list[TC]  │
│ + output_dir: Path          │
└─────────────────────────────┘

       «ABC»
┌─────────────────────────────┐
│       Tiler                 │
├─────────────────────────────┤
│ # config: TilingConfig      │
├─────────────────────────────┤
│ + split(image) → list[Tile] │
│ + merge(tiles) → Image      │
└───────────┬─────────────────┘
            │
   ┌────────┴──────────┬──────────────┐
   ▼                   ▼              ▼
RasterTiler       HilbertTiler   ZOrderTiler
                  ┌────────────────────────┐
                  │ - hc: HilbertCurve     │
                  │ - p: int               │
                  │ + order(tiles)→list    │
                  │ + inverse_order(...)   │
                  └────────────────────────┘

┌─────────────────────────────┐
│      VideoAssembler         │
├─────────────────────────────┤
│ + frames_to_video(          │
│     tiles, path) → Path     │
│ + video_to_frames(          │
│     path) → list[Tile]      │
└─────────────────────────────┘

       «ABC»
┌─────────────────────────────┐
│       Encoder               │
├─────────────────────────────┤
│ # config: EncoderConfig     │
├─────────────────────────────┤
│ + encode(src, dst) → Path   │
│ + decode(src, dst) → Path   │
│ + name() → str              │
└────────────┬────────────────┘
             │
   ┌─────────┼──────────┬──────────────┐
   ▼         ▼          ▼              ▼
HEVCEncoder VVCEncoder JPEG2000Encoder JPEGXLEncoder
  (ffmpeg    (ffmpeg/   (glymur/       (cjxl/
   libx265)  vvencapp)  imagecodecs)   imagecodecs)

┌─────────────────────────────┐
│    «dataclass»              │
│    CompressionMetrics       │
├─────────────────────────────┤
│ + original_bytes: int       │
│ + compressed_bytes: int     │
│ + bpp: float                │
│ + ratio: float              │
│ + encode_time_s: float      │
│ + decode_time_s: float      │
│ + is_lossless: bool         │
│ + image_path: Path          │
│ + encoder_name: str         │
│ + tiling_config: TC         │
└─────────────────────────────┘

┌─────────────────────────────┐
│     MetricsCalculator       │
├─────────────────────────────┤
│ + measure(original,         │
│   compressed,               │
│   decoded) → CM             │
│ + verify_lossless(a, b)→bool│
└─────────────────────────────┘

┌─────────────────────────────┐
│    CompressionPipeline      │
├─────────────────────────────┤
│ - tiler: Tiler              │
│ - assembler: VideoAssembler │
│ - encoder: Encoder          │
│ - metrics: MetricsCalc      │
├─────────────────────────────┤
│ + run(image) → CM           │
│   [split → assemble →       │
│    encode → decode →        │
│    disassemble → merge →    │
│    verify → measure]        │
└─────────────────────────────┘

┌─────────────────────────────┐
│     BenchmarkRunner         │
├─────────────────────────────┤
│ - config: BenchmarkConfig   │
│ - results: list[CM]         │
├─────────────────────────────┤
│ + run_all() → DataFrame     │
│ + build_pipeline(ec, tc)    │
│   → CompressionPipeline     │
└─────────────────────────────┘

┌─────────────────────────────┐
│     ResultsExporter         │
├─────────────────────────────┤
│ + to_csv(df, path)          │
│ + to_json(df, path)         │
│ + plot_bpp_comparison(df)   │
│ + plot_bpp_vs_tilesize(df)  │
└─────────────────────────────┘
```

---

## Przepływ danych (tryb inter-frame Hilbert)

```
PNG obraz
   │
   ▼ ImageLoader
numpy array [H × W × C]
   │
   ▼ HilbertTiler.split()
list[Tile]  (kafelki w porządku krzywej Hilberta)
   │
   ▼ VideoAssembler.frames_to_video()
frame_%04d.png → tmp/
   │
   ▼ HEVCEncoder.encode()  (ffmpeg -c:v libx265 lossless=1)
output.mkv
   │
   ▼ HEVCEncoder.decode()  (ffmpeg → frame_%04d.png)
list[Tile]  (klatki z wideo)
   │
   ▼ HilbertTiler.merge()
numpy array [H × W × C]  (rekonstrukcja)
   │
   ▼ MetricsCalculator.measure() + verify_lossless()
CompressionMetrics → BenchmarkRunner → DataFrame → CSV/wykresy
```

---

## Kroki implementacji

1. **Inicjalizacja projektu** — utwórz `requirements.txt` z zależnościami (`pillow`, `numpy`, `hilbertcurve`, `glymur`, `imagecodecs`, `pandas`, `matplotlib`, `pydantic`) i strukturę katalogów
2. **Moduł `tiling/`** — zaimplementuj `Tiler`, `RasterTiler`, `HilbertTiler` oraz `VideoAssembler`; obsłuż padding dla obrazów o wymiarach niebędących wielokrotnością kafelka
3. **Moduł `encoders/`** — zaimplementuj `Encoder` i cztery konkretne kodery wywołujące FFmpeg/CLI przez `subprocess`; obsłuż tryby FULL_IMAGE / INTRA / INTER
4. **Moduł `metrics/`** — zaimplementuj `MetricsCalculator` z weryfikacją lossless (porównanie numpy array) i pomiarem czasu
5. **`CompressionPipeline` i `BenchmarkRunner`** — połącz moduły w `pipeline.py` i `runner.py`; macierz eksperymentów z `itertools.product`
6. **CLI i raportowanie** — `scripts/run_benchmark.py` z `argparse`/`click`; `ResultsExporter` generujący CSV i wykresy porównawcze BPP

---

## Dalsze rozważania

1. **Język implementacji**: Python z wywołaniami FFmpeg/CLI przez `subprocess` jest najprostszy — odpowiedni dla projektu badawczego.
2. **Obsługa VVC true-lossless**: `vvencapp` z `TransquantBypassEnabled=1` jest wolny i wymaga konwersji YUV — warto rozważyć ograniczenie do `QP=0` jako aproksymacji i opisanie tego w pracy.
3. **Obrazy testowe**: dobór zależy od typu (medyczne/mikroskopia, tekstury, ogólne) — wpływa na zakres rozmiarów kafelków i interpretację wyników.
