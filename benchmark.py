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
	# VVC-slowness guard: honour SKIP_VVC env var to allow fast runs without VTM.
	if codec == "vvc" and os.environ.get("SKIP_VVC"):
		return False
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
				# VVC-slowness guard: warn before running any VVC experiment.
				if cfg["codec"] == "vvc":
					print(f"UWAGA: {mode} na {image} przez VTM moze byc bardzo wolne...")
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
