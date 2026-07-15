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
