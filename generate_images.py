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
