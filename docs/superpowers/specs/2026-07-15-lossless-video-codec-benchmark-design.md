# Spec: Benchmark bezstratnej kompresji obrazów kodekami wideo (HEVC/VVC)

**Data:** 2026-07-15
**Status:** Zatwierdzony do implementacji

---

## Cel

Sprawdzić, jak dobrze nowoczesne kodeki wideo (HEVC, VVC) radzą sobie z **bezstratną**
kompresją dużych obrazów statycznych w porównaniu z dedykowanymi kompresorami obrazów
(JPEG 2000, JPEG XL).

Kluczowa hipoteza do zweryfikowania: czy podzielenie dużego obrazu na kafelki, uporządkowanie
ich krzywą wypełniającą przestrzeń (Hilbert, Z-order) i potraktowanie jako sekwencji klatek
wideo — co pozwala kodekowi wykorzystać **predykcję międzyklatkową** — poprawia współczynnik
kompresji względem kompresji obrazu jako całości.

Uwaga od prowadzącego: kodeki HEVC/VVC są bardzo zaawansowane i może się okazać, że podział
obrazu **nie daje poprawy albo wręcz pogarsza** wynik. Celem jest właśnie empiryczne
sprawdzenie tego.

---

## Zakres

**W zakresie:**
- Przygotowanie zestawu obrazów: kilka naturalnych (ze zdjęć w `photos/`) + kilka syntetycznych
- Instalacja/udostępnienie narzędzi VVC (VTM: `EncoderAppStatic`/`DecoderAppStatic`) i JPEG XL (imagecodecs)
- Benchmark kompresji bezstratnej w wielu trybach (cały obraz vs. kafelki w różnych porządkach)
- Porównanie z JPEG 2000 i JPEG XL
- Metryki: BPP, współczynnik kompresji, czasy kodowania/dekodowania, weryfikacja bezstratności
- Wykresy podsumowujące

**Poza zakresem:**
- Kompresja stratna (tylko lossless)
- Obrazy RAW (brak dostępu — używamy JPG jako punktu startowego)
- GUI, API, baza danych
- Optymalizacja wydajności kodeków (używamy domyślnych/rozsądnych presetów)

---

## Założenia i ograniczenia

- **Wejście:** zdjęcia JPG w `photos/` (~4000×6000 px, RGB). JPG jest formatem stratnym, więc
  jego zdekodowane piksele traktujemy jako "oryginał" — benchmark mierzy bezstratną kompresję
  tych pikseli, nie porównuje jakości względem sceny rzeczywistej.
- **Środowisko:** Python 3.10, Linux. ffmpeg 4.4 z libx265 (HEVC) i libopenjpeg (JPEG 2000)
  są dostępne.
- **Narzędzia do doinstalowania w ramach implementacji** (kod nadal wykrywa je automatycznie i
  pomija tryb, jeśli mimo to brak — dla przenośności na inne maszyny):
  - VVC: **VTM** (VVC Test Model — oprogramowanie referencyjne JVET, licencja BSD-3-Clause-Clear),
    binaria `EncoderAppStatic` / `DecoderAppStatic`. **Uwaga:** zoptymalizowany enkoder `vvenc`
    (Fraunhofer) **nie** obsługuje prawdziwie bezstratnego kodowania (`lossless` zahardkodowane na
    `false` w źródłach, flaga `--CostMode lossless` zmienia tylko funkcję kosztu RD → błędy ±1 LSB)
    ani wejścia YUV444. Dlatego do bezstratnego VVC używamy VTM (transquant bypass + YUV444). VTM
    jest znacznie wolniejszy — akceptowalne dla benchmarku offline.
  - JPEG XL: pakiet `imagecodecs` (patrz odchylenie niżej).
- **Prostota ponad wszystko:** brak klas, pakietów, `src/`. Zwykłe funkcje w kilku skryptach.

**Odchylenie od pierwotnego spec:** (1) JPEG XL realizujemy przez `imagecodecs` (pip) zamiast CLI
`cjxl`/`djxl` — brak `cjxl` w systemie, imagecodecs daje bezstratny JXL bez budowania. (2) VVC
realizujemy przez VTM zamiast vvenc — vvenc nie potrafi prawdziwie bezstratnie (patrz wyżej).

---

## Podejście: 4 proste skrypty

Bez klas, bez pakietów Python, bez `__init__.py`. Każdy skrypt uruchamialny niezależnie.

```
hevc-vvc-lossless-image/
├── photos/                  # oryginalne JPG (niezmieniane, źródło)
├── data/                    # PNG gotowe do benchmarku (generowane raz)
│   ├── nature_P1066097.png
│   ├── nature_P1066103.png
│   ├── synth_gradient.png
│   ├── synth_noise.png
│   ├── synth_checkerboard.png
│   └── synth_repeated.png
├── results/
│   ├── results.csv          # jeden wiersz = jeden eksperyment
│   ├── bpp_by_codec.png
│   └── ratio_by_mode.png
├── generate_images.py       # krok 1: przygotuj obrazy wejściowe
├── utils.py                 # wspólne funkcje: tiling, krzywe, wywołania kodeków, metryki
├── benchmark.py             # krok 2: główna pętla eksperymentów → results.csv
├── report.py                # krok 3: wykresy z results.csv
├── requirements.txt
└── README.md
```

### Przepływ danych

```
python generate_images.py
    photos/*.jpg  → dekoduj → data/nature_*.png
    kod           → generuj → data/synth_*.png

python benchmark.py
    dla każdego data/*.png:
        dla każdego trybu (codec_mode):
            koduj → mierz rozmiar/czas → dekoduj → weryfikuj lossless
            dopisz wiersz do results/results.csv

python report.py
    results/results.csv → wykresy → results/*.png
```

---

## Komponenty

### `generate_images.py`
Przygotowuje katalog `data/` z obrazami PNG (bezstratny format pośredni).

- **Obrazy naturalne:** dekoduje wybrane JPG z `photos/` do PNG w **pełnym rozmiarze**
  (~4000×6000, bez przycinania/skalowania — prowadzący sugeruje duże obrazy). Wybieramy 2–3 zdjęcia.
- **Obrazy syntetyczne** (generowane kodem, rozmiar ~5000×5000 RGB):
  - `synth_gradient` — płynny gradient (łatwy do predykcji przestrzennej)
  - `synth_noise` — szum losowy (nieściśliwy, przypadek pesymistyczny)
  - `synth_checkerboard` — regularna szachownica (silny wzór powtarzalny)
  - `synth_repeated` — powtarzający się motyw/tekstura (symuluje "krwinki" — obiekty
    wielokrotnie występujące, gdzie predykcja międzyklatkowa może pomóc)
- Idempotentne: pomija pliki, które już istnieją w `data/`.

### `utils.py`
Wspólne funkcje (bez klas):

- **Tiling:**
  - `pad_to_grid(img, tile)` — dopełnia obraz do wielokrotności rozmiaru kafelka
  - `split_tiles(img, tile)` → lista kafelków (row-major) + zapamiętany kształt siatki
  - `merge_tiles(tiles, grid_shape, orig_shape, tile)` → rekonstrukcja obrazu
  - `crop_to_shape(img, orig_shape)` — usuwa padding
- **Porządki (kolejność kafelków):**
  - `raster_order(rows, cols)` → lista indeksów
  - `hilbert_order(rows, cols)` → lista indeksów (biblioteka `hilbertcurve`, rząd
    `p = ceil(log2(max(rows, cols)))`, punkty spoza siatki odfiltrowane)
  - `zorder_order(rows, cols)` → lista indeksów (bit-interleaving)
- **Kodeki** (każdy zwraca ścieżkę pliku skompresowanego + czasy):
  - `encode_hevc(frames_dir, out_path, inter: bool)` / `decode_hevc(...)`
  - `encode_vvc(...)` / `decode_vvc(...)` (VTM, opcjonalny)
  - `encode_jpeg2000(png_path, out_path)` / `decode_jpeg2000(...)` (Pillow)
  - `encode_jpegxl(png_path, out_path)` / `decode_jpegxl(...)` (imagecodecs, opcjonalny)
- **Wykrywanie narzędzi:** `has_tool(name)` — sprawdza dostępność `EncoderAppStatic` itd.;
  `has_module(name)` — importowalność (np. `imagecodecs`).
- **Metryki:** `bits_per_pixel(...)`, `compression_ratio(...)`, `verify_lossless(a, b)`

### `benchmark.py`
Główna pętla. Dla każdego obrazu w `data/` i każdego trybu:
1. (dla trybów kafelkowych) podziel obraz, uporządkuj, zapisz klatki PNG do temp
2. zakoduj, zmierz czas i rozmiar pliku
3. zdekoduj z powrotem do pikseli
4. zweryfikuj bezstratność (`np.array_equal`)
5. dopisz wiersz do `results/results.csv`

Odporność: jeśli tryb wymaga niedostępnego narzędzia → pomiń z ostrzeżeniem, kontynuuj.
Pliki tymczasowe (klatki, .mkv) w katalogu temp, sprzątane po każdym eksperymencie.

### `report.py`
Wczytuje `results/results.csv` (pandas) i generuje wykresy (matplotlib):
- **`bpp_by_codec.png`** — słupki BPP, klaster per obraz, słupek per codec_mode
- **`ratio_by_mode.png`** — współczynnik kompresji per tryb tilingu (żeby porównać
  full vs. intra vs. raster vs. hilbert vs. zorder)

---

## Tryby eksperymentów

Rozmiar kafelka: **256×256** (najbliższa potęga 2 do sugerowanych 250×250; wygodna dla Hilberta).

| `codec_mode`   | Codec      | Tiling  | Predykcja inter | Uwagi                          |
|----------------|------------|---------|-----------------|--------------------------------|
| `hevc_full`    | HEVC       | brak    | —               | cały obraz jako 1 klatka       |
| `hevc_intra`   | HEVC       | 256²    | nie             | kafelki jako klatki, intra-only|
| `hevc_raster`  | HEVC       | 256²    | tak             | kolejność rastrowa             |
| `hevc_hilbert` | HEVC       | 256²    | tak             | krzywa Hilberta                |
| `hevc_zorder`  | HEVC       | 256²    | tak             | Z-order                        |
| `vvc_full`     | VVC (*)    | brak    | —               | cały obraz                     |
| `vvc_hilbert`  | VVC (*)    | 256²    | tak             | krzywa Hilberta                |
| `jpeg2000`     | JPEG 2000  | brak    | —               | Pillow / libopenjpeg           |
| `jpegxl`       | JPEG XL(*) | brak    | —               | imagecodecs (lossless)         |

(*) Pomijane automatycznie, gdy narzędzie niedostępne.

---

## Model danych: `results.csv`

| kolumna       | typ    | opis                                             |
|---------------|--------|--------------------------------------------------|
| `image`       | str    | nazwa pliku PNG w `data/`                        |
| `image_type`  | str    | `nature` lub `synth`                             |
| `codec_mode`  | str    | np. `hevc_hilbert`                               |
| `tile_size`   | int    | 256 (lub 0 dla trybów full)                      |
| `n_tiles`     | int    | liczba kafelków (0 dla full)                     |
| `orig_bytes`  | int    | W × H × 3 (surowe piksele)                       |
| `comp_bytes`  | int    | rozmiar pliku skompresowanego                    |
| `bpp`         | float  | comp_bytes × 8 / (W × H)                          |
| `ratio`       | float  | orig_bytes / comp_bytes                          |
| `encode_s`    | float  | czas kodowania [s]                               |
| `decode_s`    | float  | czas dekodowania [s]                             |
| `lossless_ok` | bool   | czy rekonstrukcja == oryginał                    |

---

## Obsługa błędów

- **Brak narzędzia** (VTM/imagecodecs): wykryte na starcie, tryb pomijany z ostrzeżeniem — benchmark
  kontynuuje. Nie przerywamy całości.
- **Weryfikacja lossless nie przechodzi:** zapisujemy wiersz z `lossless_ok=False` (nie
  wyrzucamy — to jest wynik wart odnotowania), logujemy ostrzeżenie.
- **Błąd kodeka** (niezerowy exit ffmpeg): logujemy stderr, pomijamy ten eksperyment, kontynuujemy.
- **Pliki tymczasowe:** zawsze sprzątane (try/finally), nawet przy błędzie.

---

## Testowanie

Prostota projektu → testy lekkie, skupione na poprawności krytycznej logiki:

- **Round-trip tilingu:** dla każdego porządku (raster/hilbert/zorder), `merge(split(img)) == img`
  na małym obrazie RGB o niepełnej siatce (wymusza obsługę paddingu).
- **Kompletność porządków:** każdy `*_order(rows, cols)` zwraca permutację wszystkich indeksów
  siatki (każdy kafelek dokładnie raz).
- **Weryfikacja lossless na małym obrazie:** przynajmniej HEVC full + hevc_hilbert dają
  `lossless_ok=True` na małym obrazie testowym (test integracyjny, wymaga ffmpeg).

Testy uruchamiane ręcznie (pytest), nie w CI.

---

## Zależności (`requirements.txt`)

```
numpy
pillow
hilbertcurve
pandas
matplotlib
pytest
```

Narzędzia systemowe (poza pip): `ffmpeg` (z libx265, libopenjpeg). Opcjonalnie VTM
(`EncoderAppStatic`/`DecoderAppStatic`, budowane ze źródeł) dla VVC. JPEG XL przez `imagecodecs`.

---

## Kryteria sukcesu

1. `generate_images.py` tworzy `data/` z obrazami naturalnymi i syntetycznymi.
2. `benchmark.py` przechodzi przez wszystkie dostępne tryby i produkuje `results.csv`,
   gdzie wszystkie wykonane tryby lossless mają `lossless_ok=True`.
3. `report.py` generuje czytelne wykresy pozwalające ocenić hipotezę (czy tiling +
   krzywa Hilberta poprawia kompresję względem całego obrazu).
4. Kod jest prosty i czytelny — każdy skrypt < ~200 linii, zwykłe funkcje.
