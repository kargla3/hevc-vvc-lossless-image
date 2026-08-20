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

from lossless_bench.runner import BenchmarkRunner  # noqa: E402
from lossless_bench.config import BenchmarkConfig  # noqa: E402
from lossless_bench.metrics.ResultsExporter import ResultsExporter  # noqa: E402


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
	parser.add_argument(
		"--no-plots",
		action="store_true",
		help="Nie generuj wykresów PNG.",
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

	runner = BenchmarkRunner(benchmarkConfig)
	results = runner.runAll()
	reportDirectory = benchmarkConfig.output_dir / "report"
	exporter = ResultsExporter()
	if args.no_plots:
		exporter.toCsv(results, reportDirectory / "results.csv")
		exporter.toJson(results, reportDirectory / "results.json")
		exporter.toFailuresJson(runner.failures, reportDirectory / "failures.json")
		exporter.toSummary(results, runner.failures, reportDirectory / "summary.md")
	else:
		exporter.exportAll(results, reportDirectory, failures=runner.failures)

	print()
	print(f"Zakonczone eksperymenty: {len(results)}")
	print(f"Nieudane eksperymenty: {len(runner.failures)}")
	for result in results:
		status = "LOSSLESS" if result.is_lossless else (
			"NEAR-LOSSLESS" if result.max_diff <= 1 else "MISMATCH"
		)
		print(
			f"{status:13} {result.encoder_name:35} "
			f"{result.image_path.name:30} bpp={result.bpp:.3f} "
			f"ratio={result.ratio:.3f}x encode={result.encode_time_s:.2f}s"
		)
	for failure in runner.failures:
		print(f"ERROR         {failure.experiment}: {failure.error}")
	print(f"Raport: {reportDirectory}")

	return 1 if runner.failures else 0


if __name__ == "__main__":
	raise SystemExit(main())
