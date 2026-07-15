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


def test_jpeg2000_lossless_roundtrip():
    img = _small_rgb(seed=2, h=128, w=160)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.jp2")
        utils.encode_jpeg2000(img, p)
        assert os.path.getsize(p) > 0
        back = utils.decode_jpeg2000(p)
        assert utils.verify_lossless(img, back)
