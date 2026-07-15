"""Krok 3: generuje wykresy podsumowujace z results/results.csv."""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


kResultsDir = "results"
kCsvPath = os.path.join(kResultsDir, "results.csv")


def _plot_bpp_by_codec(df: pd.DataFrame) -> None:
	pivot = df.pivot_table(index="image", columns="codec_mode", values="bpp")
	ax = pivot.plot(kind="bar", figsize=(14, 7))
	ax.set_ylabel("bity na piksel (BPP)")
	ax.set_title("BPP wg obrazu i trybu kompresji (mniej = lepiej)")
	ax.legend(title="codec_mode", bbox_to_anchor=(1.01, 1), loc="upper left")
	plt.tight_layout()
	out = os.path.join(kResultsDir, "bpp_by_codec.png")
	plt.savefig(out, dpi=120)
	plt.close()
	print(f"Zapisano: {out}")


def _plot_ratio_by_mode(df: pd.DataFrame) -> None:
	means = df.groupby("codec_mode")["ratio"].mean().sort_values(ascending=False)
	ax = means.plot(kind="bar", figsize=(12, 6), color="steelblue")
	ax.set_ylabel("sredni wspolczynnik kompresji")
	ax.set_title("Sredni wspolczynnik kompresji wg trybu (wiecej = lepiej)")
	plt.tight_layout()
	out = os.path.join(kResultsDir, "ratio_by_mode.png")
	plt.savefig(out, dpi=120)
	plt.close()
	print(f"Zapisano: {out}")


def main() -> None:
	if not os.path.exists(kCsvPath):
		print(f"Brak {kCsvPath}. Uruchom najpierw benchmark.py.")
		return
	df = pd.read_csv(kCsvPath)
	if df.empty:
		print("CSV jest pusty — brak danych do wykresow.")
		return
	_plot_bpp_by_codec(df)
	_plot_ratio_by_mode(df)
	print("Gotowe.")


if __name__ == "__main__":
	main()
