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
