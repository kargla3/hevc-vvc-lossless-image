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
