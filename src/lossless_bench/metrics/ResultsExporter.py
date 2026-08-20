"""Eksport metryk benchmarku i generowanie raportow."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .CompressionMetrics import CompressionMetrics


class ResultsExporter:
	"""Zapisuje wyniki benchmarku do plikow tabelarycznych i wykresow."""

	kColumns = (
		"image_path",
		"encoder_name",
		"width",
		"height",
		"channels",
		"tile_count",
		"tile_width",
		"tile_height",
		"curve",
		"padding_mode",
		"original_bytes",
		"compressed_bytes",
		"bpp",
		"ratio",
		"encode_time_s",
		"decode_time_s",
		"is_lossless",
		"max_diff",
		"mean_diff",
		"status",
	)

	def exportAll(
		self,
		results: Iterable[CompressionMetrics],
		outputDir: str | Path,
		*,
		failures: Iterable[Any] = (),
	) -> dict[str, Path]:
		"""Eksportuje komplet wynikow i zwraca utworzone sciezki."""

		outputDirectory = Path(outputDir).expanduser()
		outputDirectory.mkdir(parents=True, exist_ok=True)
		resultList = list(results)
		failureList = list(failures)

		paths = {
			"csv": self.toCsv(resultList, outputDirectory / "results.csv"),
			"json": self.toJson(resultList, outputDirectory / "results.json"),
			"failures": self.toFailuresJson(failureList, outputDirectory / "failures.json"),
			"summary": self.toSummary(resultList, failureList, outputDirectory / "summary.md"),
		}
		paths.update(self.plotAll(resultList, outputDirectory / "figures"))
		return paths

	def toCsv(
		self,
		results: Iterable[CompressionMetrics],
		outputPath: str | Path,
	) -> Path:
		"""Zapisuje plaskie metryki do pliku CSV."""

		path = self._preparePath(outputPath)
		rows = [self._row(result) for result in results]
		with path.open("w", encoding="utf-8", newline="") as handle:
			writer = csv.DictWriter(handle, fieldnames=self.kColumns)
			writer.writeheader()
			writer.writerows(rows)
		return path

	def toJson(
		self,
		results: Iterable[CompressionMetrics],
		outputPath: str | Path,
	) -> Path:
		"""Zapisuje metryki jako tablice obiektow JSON."""

		path = self._preparePath(outputPath)
		payload = [self._row(result) for result in results]
		path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
		return path

	def toFailuresJson(self, failures: Iterable[Any], outputPath: str | Path) -> Path:
		"""Zapisuje bledy eksperymentow wraz z ich konfiguracja i typem."""

		path = self._preparePath(outputPath)
		payload = [self._failureRow(failure) for failure in failures]
		path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
		return path

	def toSummary(
		self,
		results: Iterable[CompressionMetrics],
		failures: Iterable[Any],
		outputPath: str | Path,
	) -> Path:
		"""Zapisuje czytelne podsumowanie benchmarku w Markdown."""

		path = self._preparePath(outputPath)
		resultList = list(results)
		failureList = list(failures)
		lines = [
			"# Benchmark summary",
			"",
			f"- Successful experiments: {len(resultList)}",
			f"- Failed experiments: {len(failureList)}",
			f"- Lossless results: {sum(result.is_lossless for result in resultList)}",
			f"- Near-lossless results: {sum(self._status(result) == 'NEAR-LOSSLESS' for result in resultList)}",
			"",
			"## Results",
			"",
			"| Encoder | Image | Curve | Tiles | BPP | Ratio | Encode s | Decode s | Status |",
			"|---|---|---|---:|---:|---:|---:|---:|---|",
		]
		for result in resultList:
			row = self._row(result)
			lines.append(
				f"| {result.encoder_name} | {result.image_path.name} | "
				f"{row['curve'] or 'full_image'} | {result.tile_count} | "
				f"{result.bpp:.3f} | {result.ratio:.3f} | "
				f"{result.encode_time_s:.3f} | {result.decode_time_s:.3f} | "
				f"{row['status']} |"
			)
		if failureList:
			lines.extend(("", "## Failures", ""))
			for failure in failureList:
				row = self._failureRow(failure)
				lines.append(f"- `{row['experiment']}`: {row['error_type']}: {row['error']}")

		path.write_text("\n".join(lines) + "\n", encoding="utf-8")
		return path

	def plotAll(
		self,
		results: Iterable[CompressionMetrics],
		outputDir: str | Path,
	) -> dict[str, Path]:
		"""Generuje wykresy BPP, czasu kodowania i rozmiaru pliku."""

		resultList = list(results)
		if not resultList:
			return {}
		try:
			import matplotlib.pyplot as plt
		except ImportError as error:
			raise ImportError(
				"Generating benchmark plots requires matplotlib."
			) from error

		outputDirectory = Path(outputDir).expanduser()
		outputDirectory.mkdir(parents=True, exist_ok=True)
		labels = [self._label(result) for result in resultList]
		paths: dict[str, Path] = {}
		plots = (
			("bpp", "Bits per pixel", [result.bpp for result in resultList]),
			("compressed_bytes", "Compressed bytes", [result.compressed_bytes for result in resultList]),
			("encode_time", "Encode time [s]", [result.encode_time_s for result in resultList]),
			("decode_time", "Decode time [s]", [result.decode_time_s for result in resultList]),
		)
		for name, ylabel, values in plots:
			figure, axis = plt.subplots(figsize=(max(10, len(labels) * 0.7), 6))
			axis.bar(range(len(values)), values)
			axis.set_title(ylabel)
			axis.set_ylabel(ylabel)
			axis.set_xticks(range(len(labels)), labels, rotation=75, ha="right")
			axis.grid(axis="y", alpha=0.3)
			figure.tight_layout()
			path = outputDirectory / f"{name}.png"
			figure.savefig(path, dpi=150)
			plt.close(figure)
			paths[name] = path
		return paths

	def _row(self, result: CompressionMetrics) -> dict[str, Any]:
		row = result.toDict()
		row["status"] = self._status(result)
		return {column: row.get(column) for column in self.kColumns}

	@staticmethod
	def _status(result: CompressionMetrics) -> str:
		if result.is_lossless:
			return "LOSSLESS"
		if result.max_diff <= 1:
			return "NEAR-LOSSLESS"
		return "MISMATCH"

	@staticmethod
	def _label(result: CompressionMetrics) -> str:
		curve = result.tiling_config.curve.value if result.tiling_config else "full"
		return f"{result.encoder_name}\n{curve}"

	@staticmethod
	def _failureRow(failure: Any) -> dict[str, str]:
		if isinstance(failure, dict):
			return {
				"experiment": str(failure.get("experiment", "unknown")),
				"error_type": str(failure.get("error_type", "Error")),
				"error": str(failure.get("error", failure)),
			}
		return {
			"experiment": str(getattr(failure, "experiment", "unknown")),
			"error_type": str(getattr(failure, "error_type", "Error")),
			"error": str(getattr(failure, "error", failure)),
		}

	@staticmethod
	def _preparePath(outputPath: str | Path) -> Path:
		path = Path(outputPath).expanduser()
		path.parent.mkdir(parents=True, exist_ok=True)
		return path


__all__ = ["ResultsExporter"]
