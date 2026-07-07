"""Round-trip test for image tiling.

Loads an image, splits it into tiles, merges the tiles back, and verifies that
the reconstructed image is identical to the original.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lossless_bench.image.ImageLoader import ImageLoader  # noqa: E402
from lossless_bench.image.ImageSaver import ImageSaver  # noqa: E402
from lossless_bench.tiling.HilbertTiler import HilbertTiler  # noqa: E402
from lossless_bench.tiling.RasterTiler import RasterTiler  # noqa: E402
from lossless_bench.tiling.ZOrderTiler import ZOrderTiler  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load an image, tile it, merge it back, and verify lossless round-trip."
    )
    parser.add_argument("image", type=Path, help="Input image path")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/roundtrip/reconstructed.png"),
        help="Where to save the reconstructed image",
    )
    parser.add_argument(
        "--diff-output",
        type=Path,
        default=None,
        help="Optional path to save an absolute-difference image when mismatch occurs",
    )
    parser.add_argument(
        "--tiler",
        choices=("raster", "hilbert", "zorder"),
        default="raster",
        help="Tiling order to use",
    )
    parser.add_argument("--tile-width", type=int, default=64, help="Tile width in pixels")
    parser.add_argument("--tile-height", type=int, default=64, help="Tile height in pixels")
    parser.add_argument(
        "--mode",
        choices=("L", "RGB", "RGBA", "keep"),
        default="keep",
        help="Force PIL mode before loading, or keep original",
    )
    return parser


def make_tiler(name: str, tile_width: int, tile_height: int):
    if name == "raster":
        return RasterTiler(tileHeight=tile_height, tileWidth=tile_width)
    if name == "hilbert":
        return HilbertTiler(tileHeight=tile_height, tileWidth=tile_width)
    if name == "zorder":
        return ZOrderTiler(tileHeight=tile_height, tileWidth=tile_width)
    raise ValueError(f"Unsupported tiler: {name}")


def save_diff_image(original: np.ndarray, reconstructed: np.ndarray, output_path: Path) -> Path:
    """Save a visual diff image for debugging."""

    diff = np.abs(
        reconstructed.astype(np.int16) - original.astype(np.int16)
    ).astype(np.uint8)

    if diff.ndim == 2:
        diff_image = diff
    elif diff.shape[2] == 1:
        diff_image = diff[:, :, 0]
    else:
        diff_image = diff

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(diff_image).save(output_path)
    return output_path


def main() -> int:
    args = build_parser().parse_args()

    loader = ImageLoader(targetMode=None if args.mode == "keep" else args.mode)
    saver = ImageSaver()
    tiler = make_tiler(args.tiler, args.tile_width, args.tile_height)

    original = loader.loadImage(args.image)
    tiles = tiler.splitTiles(original)
    reconstructed = tiler.mergeTiles(tiles, original.shape)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    saver.saveImage(reconstructed, args.output)

    is_exact = np.array_equal(original, reconstructed)
    diff_pixels = int(np.count_nonzero(original != reconstructed))
    max_abs_diff = int(np.max(np.abs(original.astype(np.int16) - reconstructed.astype(np.int16))))

    print(f"image: {args.image}")
    print(f"tiler: {args.tiler}")
    print(f"tile size: {args.tile_width}x{args.tile_height}")
    print(f"input shape: {original.shape}")
    print(f"tiles: {len(tiles)}")
    print(f"reconstructed: {args.output}")
    print(f"exact match: {is_exact}")
    print(f"diff pixels: {diff_pixels}")
    print(f"max abs diff: {max_abs_diff}")

    if not is_exact and args.diff_output is not None:
        diff_path = save_diff_image(original, reconstructed, args.diff_output)
        print(f"diff image: {diff_path}")

    return 0 if is_exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
