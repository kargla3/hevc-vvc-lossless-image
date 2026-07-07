from pathlib import Path

import kagglehub


def main() -> None:
	projectRoot = Path(__file__).resolve().parents[1]
	outputDir = projectRoot / "data" / "input" / "clic-dataset"
	outputDir.mkdir(parents=True, exist_ok=True)

	path = kagglehub.dataset_download(
		"mustafaalkhafaji95/clic-dataset",
		output_dir=str(outputDir),
	)

	print("Path to dataset files:", path)


if __name__ == "__main__":
	main()

