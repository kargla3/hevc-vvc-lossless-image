"""Round-trip test for lossless encoders.

Loads an image, optionally splits it into tiles ordered by a space-filling
curve, encodes and decodes it with the selected codecs, and verifies that the
reconstructed image is identical to the original.

Examples:
    python3 scripts/check_encoder_roundtrip.py data/input/photo.png
    python3 scripts/check_encoder_roundtrip.py photo.png --encoder hevc --mode intra
    python3 scripts/check_encoder_roundtrip.py photo.png --crop 1024x768 --tile-width 128
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lossless_bench.config import (  # noqa: E402
    CurveType,
    EncoderConfig,
    EncodingMode,
    TilingConfig,
)
from lossless_bench.encoders.HEVCEncoder import HEVCEncoder  # noqa: E402
from lossless_bench.encoders.JPEG2000Encoder import JPEG2000Encoder  # noqa: E402
from lossless_bench.encoders.JPEGXLEncoder import JPEGXLEncoder  # noqa: E402
from lossless_bench.encoders.VVCEncoder import VVCEncoder  # noqa: E402
from lossless_bench.image.ImageLoader import ImageLoader  # noqa: E402
from lossless_bench.image.ImageSaver import ImageSaver  # noqa: E402
from lossless_bench.metrics.CompressionMetrics import CompressionMetrics  # noqa: E402
from lossless_bench.metrics.MetricsCalculator import (  # noqa: E402
    MetricsCalculator,
    measureDuration,
)
from lossless_bench.tiling.HilbertTiler import HilbertTiler  # noqa: E402
from lossless_bench.tiling.RasterTiler import RasterTiler  # noqa: E402
from lossless_bench.tiling.Tiler import Tile  # noqa: E402
from lossless_bench.tiling.VideoAssembler import VideoAssembler  # noqa: E402
from lossless_bench.tiling.ZOrderTiler import ZOrderTiler  # noqa: E402


ENCODER_NAMES = ("hevc", "vvc", "jpeg2000", "jpegxl")

# VVenC has no true lossless mode (no TransquantBypass), so QP 0 is only an
# approximation and small per-pixel differences are expected, not a failure.
NEAR_LOSSLESS_ENCODERS = {"vvc"}

CURVE_BY_TILER = {
    "raster": CurveType.RASTER,
    "hilbert": CurveType.HILBERT,
    "zorder": CurveType.Z_ORDER,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Encode and decode an image, then verify the lossless round-trip."
    )
    parser.add_argument("image", type=Path, help="Input image path")
    parser.add_argument(
        "--encoder",
        choices=(*ENCODER_NAMES, "all"),
        default="all",
        help="Which encoder to run (default: all)",
    )
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in EncodingMode),
        default=EncodingMode.INTER.value,
        help="Encoding mode: full_image encodes the whole image, "
        "intra/inter encode tiles as video frames (default: inter)",
    )
    parser.add_argument(
        "--tiler",
        choices=("raster", "hilbert", "zorder"),
        default="hilbert",
        help="Tile ordering used in intra/inter modes (default: hilbert)",
    )
    parser.add_argument("--tile-width", type=int, default=64, help="Tile width in pixels")
    parser.add_argument("--tile-height", type=int, default=64, help="Tile height in pixels")
    parser.add_argument(
        "--preset",
        default="medium",
        help="Encoder preset (default: medium)",
    )
    parser.add_argument(
        "--crop",
        default=None,
        help="Encode only the top-left WxH region, e.g. 1024x768 (useful for quick checks "
        "on very large photos)",
    )
    parser.add_argument(
        "--mode-image",
        choices=("L", "RGB", "keep"),
        default="keep",
        help="Force PIL mode before loading, or keep the original",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/encoder_roundtrip"),
        help="Where to write frames, bitstreams and reconstructions",
    )
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="Keep files from a previous run instead of clearing the output directory",
    )
    parser.add_argument(
        "--save-reconstruction",
        action="store_true",
        help="Save the reconstructed image next to the bitstream",
    )
    parser.add_argument(
        "--vvenc-path",
        default=os.environ.get("VVENC_PATH", "vvencapp"),
        help="Path to the vvencapp binary (default: $VVENC_PATH or vvencapp)",
    )
    parser.add_argument(
        "--vvdec-path",
        default=os.environ.get("VVDEC_PATH", "vvdecapp"),
        help="Path to the vvdecapp binary (default: $VVDEC_PATH or vvdecapp)",
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


def make_tiling_config(args: argparse.Namespace) -> TilingConfig | None:
    """Describes the tiling used, or None when the whole image is encoded at once."""

    if EncodingMode(args.mode) is EncodingMode.FULL_IMAGE:
        return None

    return TilingConfig(
        tile_width=args.tile_width,
        tile_height=args.tile_height,
        curve=CURVE_BY_TILER[args.tiler],
    )


def make_encoder(name: str, args: argparse.Namespace):
    mode = EncodingMode(args.mode)
    if name == "hevc":
        return HEVCEncoder(EncoderConfig(codec="hevc", mode=mode, preset=args.preset))
    if name == "vvc":
        return VVCEncoder(
            EncoderConfig(codec="vvc", mode=mode, preset=args.preset),
            encoderPath=args.vvenc_path,
            decoderPath=args.vvdec_path,
        )
    if name == "jpeg2000":
        return JPEG2000Encoder(EncoderConfig(codec="jpeg2000", mode=mode, preset=args.preset))
    if name == "jpegxl":
        return JPEGXLEncoder(EncoderConfig(codec="jpegxl", mode=mode, preset=args.preset))
    raise ValueError(f"Unsupported encoder: {name}")


def parse_crop(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None

    parts = value.lower().split("x")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Invalid --crop value: {value}. Expected WxH, for example 1024x768.")

    width, height = int(parts[0]), int(parts[1])
    if width <= 0 or height <= 0:
        raise ValueError("--crop width and height must be greater than 0")
    return width, height


def encode_source(image: np.ndarray, args: argparse.Namespace, work_dir: Path):
    """Prepares encoder input: the image itself or a directory of tile frames."""

    if EncodingMode(args.mode) is EncodingMode.FULL_IMAGE:
        image_path = work_dir / "source.png"
        ImageSaver().saveImage(image, image_path)
        return image_path, None

    tiler = make_tiler(args.tiler, args.tile_width, args.tile_height)
    tiles = tiler.splitTiles(image)
    frames_dir = VideoAssembler().framesToVideo(tiles, work_dir / "frames")
    return frames_dir, (tiler, tiles)


def restore_image(
    decoded_dir: Path,
    tiling,
    original_shape: tuple[int, ...],
) -> np.ndarray:
    """Rebuilds the image from decoded frames."""

    frames = VideoAssembler().videoToFrames(decoded_dir)
    if tiling is None:
        if len(frames) != 1:
            raise ValueError(f"Expected a single decoded frame, got {len(frames)}")
        return frames[0]

    tiler, tiles = tiling
    if len(frames) != len(tiles):
        raise ValueError(f"Expected {len(tiles)} decoded frames, got {len(frames)}")

    restored_tiles = [
        Tile(row=tile.row, col=tile.col, data=frame) for tile, frame in zip(tiles, frames)
    ]
    return tiler.mergeTiles(restored_tiles, original_shape)


def run_encoder(
    name: str, image: np.ndarray, args: argparse.Namespace
) -> CompressionMetrics:
    work_dir = args.output_dir / name
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    encoder = make_encoder(name, args)
    source, tiling = encode_source(image, args, work_dir)

    with measureDuration() as encode_duration:
        bitstream = encoder.encode(source, work_dir / "bitstream")

    with measureDuration() as decode_duration:
        decoded_dir = encoder.decode(bitstream, work_dir / "decoded")

    restored = restore_image(decoded_dir, tiling, image.shape)
    if args.save_reconstruction:
        ImageSaver().saveImage(restored, work_dir / "reconstructed.png")

    calculator = MetricsCalculator()
    return calculator.measureCompression(
        original=image,
        restored=restored,
        compressedBytes=calculator.measureBitstreamBytes(bitstream),
        encodeTime=encode_duration.seconds,
        decodeTime=decode_duration.seconds,
        imagePath=args.image,
        encoderName=encoder.getName(),
        tilingConfig=make_tiling_config(args),
        tileCount=len(tiling[1]) if tiling is not None else 1,
    )


def main() -> int:
    args = build_parser().parse_args()

    loader = ImageLoader(targetMode=None if args.mode_image == "keep" else args.mode_image)
    image = loader.loadImage(args.image)

    crop = parse_crop(args.crop)
    if crop is not None:
        width, height = crop
        image = image[:height, :width, ...]

    if args.output_dir.exists() and not args.keep_output:
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    encoder_names = ENCODER_NAMES if args.encoder == "all" else (args.encoder,)
    raw_bytes = image.size

    print(f"image:      {args.image}")
    print(f"shape:      {image.shape} ({raw_bytes / 1e6:.1f} MB uncompressed)")
    print(f"mode:       {args.mode}")
    if EncodingMode(args.mode) is not EncodingMode.FULL_IMAGE:
        print(f"tiling:     {args.tiler} {args.tile_width}x{args.tile_height}")
    print(f"preset:     {args.preset}")
    print(f"output:     {args.output_dir}")
    print()

    header = (
        f"{'encoder':<34} {'tiles':>6} {'bytes':>11} {'bpp':>7} {'ratio':>7} "
        f"{'enc s':>7} {'dec s':>7}  result"
    )
    print(header)
    print("-" * len(header))

    failures: list[str] = []
    for name in encoder_names:
        try:
            metrics = run_encoder(name, image, args)
        except Exception as error:  # noqa: BLE001 - report and continue with the next codec
            print(f"{name:<34} {'-':>6} {'-':>11} {'-':>7} {'-':>7} {'-':>7} {'-':>7}  ERROR")
            print(f"    {type(error).__name__}: {error}")
            failures.append(name)
            continue

        if metrics.is_lossless:
            verdict = "LOSSLESS"
        elif name in NEAR_LOSSLESS_ENCODERS:
            verdict = f"near-lossless (max {metrics.max_diff}, mean {metrics.mean_diff:.4f})"
        else:
            verdict = f"MISMATCH (max {metrics.max_diff}, mean {metrics.mean_diff:.4f})"
            failures.append(name)

        print(
            f"{metrics.encoder_name:<34} {metrics.tile_count:>6} {metrics.compressed_bytes:>11} "
            f"{metrics.bpp:>7.3f} {metrics.ratio:>6.2f}x {metrics.encode_time_s:>7.2f} "
            f"{metrics.decode_time_s:>7.2f}  {verdict}"
        )

    print()
    if failures:
        print(f"problems with: {', '.join(failures)}")
        return 1

    print("all encoders reconstructed the image as expected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
