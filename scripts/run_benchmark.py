"""CLI do uruchamiania benchmarków."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


kRootDir = Path(__file__).resolve().parents[1]
kSrcDir = kRootDir / "src"
if str(kSrcDir) not in sys.path:
	sys.path.insert(0, str(kSrcDir))

from lossless_bench.config import BenchmarkConfig  # noqa: E402


kSupportedConfigSuffixes = {".json", ".yaml", ".yml"}


def buildParser() -> argparse.ArgumentParser:
	"""Buduje parser argumentów CLI."""

	parser = argparse.ArgumentParser(description="Uruchamia eksperymenty benchmarkowe.")
	parser.add_argument(
		"--config",
		type=Path,
		required=True,
		help="Ścieżka do pliku konfiguracyjnego JSON.",
	)
	return parser


def loadConfig(configPath: Path) -> BenchmarkConfig:
	"""Wczytuje konfigurację benchmarku z pliku YAML albo JSON."""

	if not configPath.exists():
		raise FileNotFoundError(f"Configuration file not found: {configPath}")
	if not configPath.is_file():
		raise IsADirectoryError(f"Expected a file, got a directory: {configPath}")
	if configPath.suffix.lower() not in kSupportedConfigSuffixes:
		raise ValueError(
			f"Unsupported config format: {configPath.suffix}. "
			f"Supported formats: {sorted(kSupportedConfigSuffixes)}"
		)

	with configPath.open("r", encoding="utf-8") as handle:
		if configPath.suffix.lower() == ".json":
			rawConfig = json.load(handle)
		else:
			rawConfig = yaml.safe_load(handle)

	if not isinstance(rawConfig, dict):
		raise ValueError(f"Invalid configuration structure in file: {configPath}")

	return BenchmarkConfig.fromDict(rawConfig)


def main() -> int:
	"""Uruchamia CLI benchmarku."""

	args = buildParser().parse_args()
	benchmarkConfig = loadConfig(args.config)

	print("Konfiguracja benchmarku została wczytana poprawnie.")
	print(f"Liczba obrazów: {len(benchmarkConfig.image_paths)}")
	print(f"Liczba konfiguracji enkoderów: {len(benchmarkConfig.encoder_configs)}")
	print(f"Liczba konfiguracji tilingu: {len(benchmarkConfig.tiling_configs)}")
	print(f"Katalog wyjściowy: {benchmarkConfig.output_dir}")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
