"""Self-check for the metrics module.

Runs assertions on synthetic arrays and temporary bitstream directories, prints
a table of results, and exits with 0 only when every check passes.

Usage:
    python3 scripts/check_metrics.py
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from lossless_bench.config import CurveType, TilingConfig  # noqa: E402
from lossless_bench.metrics.CompressionMetrics import CompressionMetrics  # noqa: E402
from lossless_bench.metrics.MetricsCalculator import (  # noqa: E402
    MetricsCalculator,
    measureDuration,
)


CHECKS: list[tuple[str, object]] = []


def check(name: str):
    """Registers a check function under a readable name."""

    def decorator(function):
        CHECKS.append((name, function))
        return function

    return decorator


def expect(condition: bool, detail: str) -> None:
    """Fails the current check when the condition does not hold."""

    if not condition:
        raise AssertionError(detail)


def expect_raises(exception_type, function, detail: str) -> None:
    """Fails the current check unless the call raises the expected exception."""

    try:
        function()
    except exception_type:
        return
    except Exception as error:  # noqa: BLE001 - wrong exception type is a failure
        raise AssertionError(f"{detail}: got {type(error).__name__}: {error}") from error
    raise AssertionError(f"{detail}: no exception raised")


def make_metrics(tiling_config: TilingConfig | None) -> CompressionMetrics:
    """Builds a CompressionMetrics instance with fixed, easy-to-check values."""

    return CompressionMetrics(
        original_bytes=60,
        compressed_bytes=10,
        bpp=4.0,
        ratio=6.0,
        encode_time_s=1.5,
        decode_time_s=0.5,
        is_lossless=True,
        image_path=Path("data/input/photo.png"),
        encoder_name="HEVC (libx265)",
        tiling_config=tiling_config,
        max_diff=0,
        mean_diff=0.0,
        tile_count=42,
        width=5,
        height=4,
        channels=3,
    )


@check("toDict with tiling config")
def check_to_dict_with_tiling() -> None:
    tiling_config = TilingConfig(tile_width=64, tile_height=32, curve=CurveType.HILBERT)
    row = make_metrics(tiling_config).toDict()

    expect(
        row["image_path"] == "data/input/photo.png",
        f"image_path not a str: {row['image_path']!r}",
    )
    expect(row["bpp"] == 4.0, f"bpp changed: {row['bpp']}")
    expect(row["tile_width"] == 64, f"tile_width not unpacked: {row['tile_width']!r}")
    expect(row["tile_height"] == 32, f"tile_height not unpacked: {row['tile_height']!r}")
    expect(row["curve"] == "hilbert", f"curve not a plain string: {row['curve']!r}")
    expect(
        row["padding_mode"] == "constant",
        f"padding_mode missing: {row['padding_mode']!r}",
    )
    expect("tiling_config" not in row, "toDict must flatten tiling_config, not nest it")


@check("toDict without tiling config")
def check_to_dict_without_tiling() -> None:
    row = make_metrics(None).toDict()

    for key in ("tile_width", "tile_height", "curve", "padding_mode"):
        expect(key in row, f"missing key {key} for full_image mode")
        expect(row[key] is None, f"{key} should be None for full_image, got {row[key]!r}")


@check("identical images are lossless")
def check_identical_images() -> None:
    calculator = MetricsCalculator()
    original = np.arange(60, dtype=np.uint8).reshape(4, 5, 3)
    restored = original.copy()

    expect(
        calculator.verifyLossless(original, restored) is True,
        "identical arrays reported as lossy",
    )

    difference = calculator.compareImages(original, restored)
    expect(difference.is_lossless is True, "is_lossless should be True")
    expect(difference.max_diff == 0, f"max_diff should be 0, got {difference.max_diff}")
    expect(difference.mean_diff == 0.0, f"mean_diff should be 0.0, got {difference.mean_diff}")


@check("single differing pixel is detected")
def check_single_pixel_difference() -> None:
    calculator = MetricsCalculator()
    original = np.zeros((4, 5, 3), dtype=np.uint8)
    restored = original.copy()
    restored[2, 3, 1] = 7

    expect(calculator.verifyLossless(original, restored) is False, "difference not detected")

    difference = calculator.compareImages(original, restored)
    expect(difference.is_lossless is False, "is_lossless should be False")
    expect(difference.max_diff == 7, f"max_diff should be 7, got {difference.max_diff}")

    expected_mean = 7 / 60
    expect(
        abs(difference.mean_diff - expected_mean) < 1e-12,
        f"mean_diff should be {expected_mean}, got {difference.mean_diff}",
    )


@check("uint8 difference does not wrap around")
def check_no_wraparound() -> None:
    calculator = MetricsCalculator()
    original = np.zeros((2, 2), dtype=np.uint8)
    restored = np.full((2, 2), 255, dtype=np.uint8)

    difference = calculator.compareImages(original, restored)
    expect(difference.max_diff == 255, f"max_diff should be 255, got {difference.max_diff}")
    expect(
        difference.mean_diff == 255.0,
        f"mean_diff should be 255.0, got {difference.mean_diff}",
    )


@check("mismatched images are rejected")
def check_comparison_rejects_bad_input() -> None:
    calculator = MetricsCalculator()
    original = np.zeros((4, 5, 3), dtype=np.uint8)

    expect_raises(
        ValueError,
        lambda: calculator.compareImages(original, np.zeros((4, 6, 3), dtype=np.uint8)),
        "different shapes must raise ValueError, not return False",
    )
    expect_raises(
        ValueError,
        lambda: calculator.compareImages(original, np.zeros((4, 5, 3), dtype=np.uint16)),
        "different dtypes must raise ValueError",
    )
    expect_raises(
        ValueError,
        lambda: calculator.compareImages(
            np.zeros((2, 2, 3, 1), dtype=np.uint8), np.zeros((2, 2, 3, 1), dtype=np.uint8)
        ),
        "4D array must raise ValueError",
    )
    expect_raises(
        ValueError,
        lambda: calculator.compareImages(
            np.zeros((0, 5, 3), dtype=np.uint8), np.zeros((0, 5, 3), dtype=np.uint8)
        ),
        "empty image must raise ValueError",
    )


@check("measureDuration records elapsed time")
def check_measure_duration() -> None:
    with measureDuration() as duration:
        total = sum(range(10000))

    expect(total == 49995000, "loop body did not run")
    expect(duration.seconds >= 0.0, f"seconds must not be negative, got {duration.seconds}")

    try:
        with measureDuration() as failed:
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    expect(failed.seconds >= 0.0, "duration must be recorded even when the block raises")


@check("bitstream size skips sidecar files")
def check_bitstream_directory() -> None:
    calculator = MetricsCalculator()

    with tempfile.TemporaryDirectory() as raw_directory:
        directory = Path(raw_directory)
        (directory / "frame_0000.265").write_bytes(b"x" * 100)
        (directory / "frame_0001.265").write_bytes(b"x" * 40)
        (directory / "meta.json").write_bytes(b"x" * 500)

        total = calculator.measureBitstreamBytes(directory)
        expect(total == 140, f"expected 140 bytes from .265 files only, got {total}")


@check("bitstream size handles files and bad paths")
def check_bitstream_file_and_errors() -> None:
    calculator = MetricsCalculator()

    with tempfile.TemporaryDirectory() as raw_directory:
        directory = Path(raw_directory)

        single = directory / "stream.jxl"
        single.write_bytes(b"x" * 33)
        size = calculator.measureBitstreamBytes(single)
        expect(size == 33, f"expected 33 bytes for a single file, got {size}")

        empty = directory / "empty"
        empty.mkdir()
        (empty / "notes.txt").write_bytes(b"x" * 10)
        expect_raises(
            ValueError,
            lambda: calculator.measureBitstreamBytes(empty),
            "directory without bitstream files must raise ValueError",
        )

        expect_raises(
            FileNotFoundError,
            lambda: calculator.measureBitstreamBytes(directory / "missing"),
            "missing path must raise FileNotFoundError",
        )


@check("measureCompression computes bpp and ratio")
def check_measure_compression() -> None:
    calculator = MetricsCalculator()
    original = np.zeros((4, 5, 3), dtype=np.uint8)
    restored = original.copy()
    tiling_config = TilingConfig(tile_width=64, tile_height=64, curve=CurveType.HILBERT)

    metrics = calculator.measureCompression(
        original=original,
        restored=restored,
        compressedBytes=10,
        encodeTime=1.5,
        decodeTime=0.5,
        imagePath="data/input/photo.png",
        encoderName="HEVC (libx265)",
        tilingConfig=tiling_config,
        tileCount=42,
    )

    # 4x5 pikseli, 3 kanaly, uint8 -> 60 bajtow surowych danych, 20 pikseli
    expect(
        metrics.original_bytes == 60,
        f"original_bytes should be 60, got {metrics.original_bytes}",
    )
    expect(metrics.bpp == 4.0, f"bpp should be 10*8/20 = 4.0, got {metrics.bpp}")
    expect(metrics.ratio == 6.0, f"ratio should be 60/10 = 6.0, got {metrics.ratio}")
    expect(metrics.width == 5, f"width should be 5, got {metrics.width}")
    expect(metrics.height == 4, f"height should be 4, got {metrics.height}")
    expect(metrics.channels == 3, f"channels should be 3, got {metrics.channels}")
    expect(metrics.tile_count == 42, f"tile_count should be 42, got {metrics.tile_count}")
    expect(metrics.is_lossless is True, "identical arrays should be lossless")
    expect(metrics.max_diff == 0, f"max_diff should be 0, got {metrics.max_diff}")
    expect(
        metrics.image_path == Path("data/input/photo.png"),
        f"image_path: {metrics.image_path}",
    )
    expect(metrics.tiling_config is tiling_config, "tiling_config should be stored unchanged")


@check("measureCompression handles grayscale and uint16")
def check_measure_compression_shapes() -> None:
    calculator = MetricsCalculator()

    grayscale = np.zeros((4, 5), dtype=np.uint8)
    metrics = calculator.measureCompression(
        original=grayscale,
        restored=grayscale.copy(),
        compressedBytes=5,
        encodeTime=0.0,
        decodeTime=0.0,
        imagePath="photo.png",
        encoderName="JPEG XL",
    )
    expect(metrics.channels == 1, f"2D array means 1 channel, got {metrics.channels}")
    expect(
        metrics.original_bytes == 20,
        f"original_bytes should be 20, got {metrics.original_bytes}",
    )
    expect(metrics.tile_count == 1, f"tile_count defaults to 1, got {metrics.tile_count}")
    expect(metrics.tiling_config is None, "tiling_config defaults to None")

    # uint16 zajmuje dwa bajty na probke: 4*5*2 = 40, a nie 20
    deep = np.zeros((4, 5), dtype=np.uint16)
    deep_metrics = calculator.measureCompression(
        original=deep,
        restored=deep.copy(),
        compressedBytes=5,
        encodeTime=0.0,
        decodeTime=0.0,
        imagePath="photo.png",
        encoderName="JPEG XL",
    )
    expect(
        deep_metrics.original_bytes == 40,
        f"uint16 original_bytes should be 40, got {deep_metrics.original_bytes}",
    )


@check("measureCompression rejects impossible arguments")
def check_measure_compression_errors() -> None:
    calculator = MetricsCalculator()
    original = np.zeros((4, 5, 3), dtype=np.uint8)

    def call(**overrides):
        arguments = {
            "original": original,
            "restored": original.copy(),
            "compressedBytes": 10,
            "encodeTime": 1.0,
            "decodeTime": 1.0,
            "imagePath": "photo.png",
            "encoderName": "HEVC (libx265)",
        }
        arguments.update(overrides)
        return lambda: calculator.measureCompression(**arguments)

    expect_raises(ValueError, call(compressedBytes=0), "compressedBytes=0 must raise ValueError")
    expect_raises(
        ValueError, call(compressedBytes=-5), "negative compressedBytes must raise ValueError"
    )
    expect_raises(ValueError, call(tileCount=0), "tileCount=0 must raise ValueError")
    expect_raises(ValueError, call(encodeTime=-1.0), "negative encodeTime must raise ValueError")


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="Verify the metrics module on synthetic data.")


def main() -> int:
    build_parser().parse_args()

    failures = 0
    name_width = max(len(name) for name, _ in CHECKS)
    for name, function in CHECKS:
        try:
            function()
        except AssertionError as error:
            print(f"{name:<{name_width}}  FAIL   {error}")
            failures += 1
        except Exception as error:  # noqa: BLE001 - report and continue with the next check
            print(f"{name:<{name_width}}  ERROR  {type(error).__name__}: {error}")
            failures += 1
        else:
            print(f"{name:<{name_width}}  ok")

    print()
    if failures:
        print(f"{failures} of {len(CHECKS)} checks failed")
        return 1

    print(f"all {len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
