# hevc-vvc-lossless-image

## Zastosowanie algorytmów kompresji wideo HEVC i VVC do bezstratnej kompresji obrazów statycznych dużej wielkości

Celem jest sprawdzenie, jak dobrze do kompresji bezstratnej dużych obrazów nadają się najnowocześniejsze algorytmy kompresji wideo, tzn. HEVC i VVC, które zdolne są bezstratnie kompresować obrazy i wideo, jednak ich głównym przeznaczeniem jest stratna kompresja wideo. W ramach tematu należy sprawdzić koncepcję poprawy wyników kompresji bezstratnej obrazu przez podzielenie obrazu siatką prostokątną na fragmenty, przeglądane za pomocą krzywej wypełniającej przestrzeń (jak np. krzywa Hilberta) i traktowane jako klatki wideo. Algorytmy kompresji wideo posiadają bardzo rozbudowane mechanizmy predykcji międzyklatkowej (predykcji ruchu), co powinno umożliwić poprawę współczynników dla niektórych typów obrazów (zawierających tekstury lub wielokrotnie występujące obiekty, jak krwinki w zdjęciach medycznych). Należy porównać tak uzyskane wyniki z wynikami kompresji obrazu jako całości za pomocą ww. algorytmów kompresji wideo oraz kompresorów dedykowanych do obrazów (JPEG 2000, JPEG XL).

---

## Uruchamianie i praca

### Wymagania

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/) z obsługą `libx265` i `libvvenc` (dostępny w `PATH`)
- Opcjonalnie: `cjxl` / `djxl` z [libjxl](https://github.com/libjxl/libjxl/releases) (dostępne w `PATH`)

### Konfiguracja środowiska

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/Karoo/hevc-vvc-lossless-image.git
cd hevc-vvc-lossless-image

# 2. Utwórz środowisko wirtualne
python -m venv .venv

# 3. Aktywuj środowisko

# Windows PowerShell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1

# Windows cmd
.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate

# 4. Zainstaluj zależności
pip install -r requirements.txt

# 5. Pobierz obrazy z datasetu
python3 .\scripts\load_dataset.py
```

### Uruchomienie benchmarku

# TODO
```bash
python -m lossless_bench run --config config.yaml
```

---

## Dokumentacja

Szczegółowy plan architektury, diagram klas i opis modułów znajduje się w [plan/plan.md](plan/plan.md).