"""Encoder abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import subprocess
from typing import Sequence

from ..config import EncoderConfig


class Encoder(ABC):
	"""Bazowa klasa dla wszystkich enkoderów używanych w benchmarku."""

	def __init__(self, config: EncoderConfig) -> None:
		if not isinstance(config, EncoderConfig):
			raise TypeError("config must be an EncoderConfig instance")
		self._config = config

	@property
	def config(self) -> EncoderConfig:
		"""Zwraca konfigurację enkodera."""

		return self._config

	@property
	def codec(self) -> str:
		"""Zwraca nazwę kodeka z konfiguracji."""

		return self._config.codec

	@property
	def mode(self):
		"""Zwraca tryb pracy enkodera."""

		return self._config.mode

	@property
	def preset(self) -> str:
		"""Zwraca preset enkodera."""

		return self._config.preset

	@property
	def extraParams(self) -> dict:
		"""Zwraca dodatkowe parametry enkodera."""

		return self._config.extra_params

	@abstractmethod
	def encode(self, src: str | Path, dst: str | Path) -> Path:
		"""Koduje wejście do docelowego pliku."""

	@abstractmethod
	def decode(self, src: str | Path, dst: str | Path) -> Path:
		"""Dekoduje wejście do docelowego pliku."""

	@abstractmethod
	def getName(self) -> str:
		"""Zwraca nazwę enkodera używaną w raportach."""

	def _normalizePath(self, path: str | Path) -> Path:
		"""Normalizuje ścieżkę wejściową bez sprawdzania istnienia."""

		return Path(path).expanduser()

	def _ensureParentDirectory(self, path: Path) -> Path:
		"""Tworzy katalog nadrzędny dla ścieżki wyjściowej."""

		path.parent.mkdir(parents=True, exist_ok=True)
		return path

	def _runCommand(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
		"""Uruchamia komendę i podnosi czytelny wyjątek przy błędzie."""

		try:
			return subprocess.run(
				list(command),
				check=True,
				capture_output=True,
				text=True,
			)
		except FileNotFoundError as error:
			raise FileNotFoundError(
				"Required external command was not found in PATH."
			) from error
		except subprocess.CalledProcessError as error:
			stderr = error.stderr.strip() if error.stderr else ""
			raise RuntimeError(
				f"Encoder command failed with exit code {error.returncode}: {stderr}"
			) from error


__all__ = ["Encoder"]
