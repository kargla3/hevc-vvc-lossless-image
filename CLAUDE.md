# CLAUDE.md

This file provides quidance to Claude Code when working in this repository. 

## Project Overview

Celem jest sprawdzenie, jak dobrze do kompresji bezstratnej dużych obrazów nadają się najnowocześniejsze algorytmy kompresji wideo, tzn. HEVC i VVC, które zdolne są bezstratnie kompresować obrazy i wideo, jednak ich głównym przeznaczeniem jest stratna kompresja wideo. W ramach tematu należy sprawdzić koncepcję poprawy wyników kompresji bezstratnej obrazu przez podzielenie obrazu siatką prostokątną na fragmenty, przeglądane za pomocą krzywej wypełniającej przestrzeń (jak np. krzywa Hilberta) i traktowane jako klatki wideo. Algorytmy kompresji wideo posiadają bardzo rozbudowane mechanizmy predykcji międzyklatkowej (predykcji ruchu), co powinno umożliwić poprawę współczynników dla niektórych typów obrazów (zawierających tekstury lub wielokrotnie występujące obiekty, jak krwinki w zdjęciach medycznych). Należy porównać tak uzyskane wyniki z wynikami kompresji obrazu jako całości za pomocą ww. algorytmów kompresji wideo oraz kompresorów dedykowanych do obrazów (JPEG 2000, JPEG XL).

Uwaga od prowadzącego: kodeki HEVC/VVC są bardzo zaawansowane i może się okazać, że podział dużego obrazu na kafelki nie daje poprawy albo wręcz pogarsza współczynnik — celem tematu jest empiryczne sprawdzenie tego. Do badań wystarczy kilka obrazów: kilka naturalnych i kilka wygenerowanych sztucznie, duże (np. 5000×5000, siatka o oczkach ~250×250 dobrana tak, by dała się przeglądać krzywą Hilberta).

## Tech stack

- Python 3.10

## Architektura (podejście: prostota ponad wszystko)

Projekt to **4 proste skrypty** — bez klas, bez pakietów, bez `src/` czy `__init__.py`. Zwykłe funkcje. Każdy skrypt uruchamialny niezależnie.

- `generate_images.py` — dekoduje wybrane JPG z `photos/` → `data/nature_*.png` oraz generuje `data/synth_*.png` (gradient, szum, szachownica, powtarzalny motyw)
- `utils.py` — wspólne funkcje: tiling, porządki (raster/hilbert/zorder), wywołania kodeków, metryki
- `benchmark.py` — główna pętla: każdy obraz × każdy `codec_mode` → koduj → dekoduj → weryfikuj lossless → `results/results.csv`
- `report.py` — wczytuje CSV → wykresy do `results/`

Pełny spec: [docs/superpowers/specs/2026-07-15-lossless-video-codec-benchmark-design.md](docs/superpowers/specs/2026-07-15-lossless-video-codec-benchmark-design.md)

### Kontekst historyczny

Pliki w historii gita (`src/lossless_bench/…`, `config.yaml`, `plan/plan.md`) to **porzucona wcześniejsza próba** (przekombinowana architektura klas). Nie kontynuujemy jej — zaczynamy od zera z prostą strukturą powyżej.

## Dane wejściowe

- `photos/` — 9 zdjęć (~4000×6000 px, RGB), każde w formatach `.jpg`, `.jp2`, `.jxl`. Pracujemy **tylko na tych zdjęciach**.
- JPG jest stratny — jego zdekodowane piksele traktujemy jako "oryginał". Brak dostępu do RAW.

## Kodeki i narzędzia

- **HEVC** ✅ — `ffmpeg` + libx265 (dostępne)
- **JPEG 2000** ✅ — Pillow + libopenjpeg (dostępne)
- **VVC** ❌ — `vvencapp`/`vvdecapp` niezainstalowane (do doinstalowania)
- **JPEG XL** ❌ — `cjxl`/`djxl` niezainstalowane; Pillow nie obsługuje JXL (do doinstalowania)

Tryby wymagające niedostępnych narzędzi są **automatycznie pomijane** z ostrzeżeniem (benchmark nie przerywa się).

Tryby (`codec_mode`): `hevc_full`, `hevc_intra`, `hevc_raster`, `hevc_hilbert`, `hevc_zorder`, `vvc_full`, `vvc_hilbert`, `jpeg2000`, `jpegxl`. Rozmiar kafelka: **256×256**.

## Konwencje

- Kod prosty i czytelny, każdy skrypt < ~200 linii, zwykłe funkcje (snake_case), bez klas.
- Komentarze i komunikaty po polsku (zgodnie z istniejącym stylem repo).