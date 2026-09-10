from pathlib import Path
from typing import Protocol

import pandas as pd

WAVPACK_COMPRESS_OPTIONS = ("--pair-unassigned-chans", "--threads=12")
WAVPACK_DECOMPRESS_OPTIONS = ("--threads=12",)


class Backend(Protocol):
    """A CLI compression tool, driven through argv."""

    name: str
    extension: str

    def compress_command(
        self, bin_path: Path, out_path: Path, meta: pd.Series, options: list[str]
    ) -> list[str]: ...

    def decompress_command(
        self, compressed_path: Path, out_path: Path, options: list[str]
    ) -> list[str]: ...

    def verify_command(
        self, compressed_path: Path, options: list[str]
    ) -> list[str] | None: ...


class WavPackBackend:
    """https://www.wavpack.com/wavpack_doc.html"""

    name = "wavpack"
    extension = ".wv"
    default_compress_options = list(WAVPACK_COMPRESS_OPTIONS)
    default_decompress_options = list(WAVPACK_DECOMPRESS_OPTIONS)

    def __init__(self, executable: str = "wavpack", decoder: str = "wvunpack"):
        self.executable = executable
        self.decoder = decoder

    def compress_command(
        self, bin_path: Path, out_path: Path, meta: pd.Series, options: list[str]
    ) -> list[str]:
        raw_pcm = (
            f"--raw-pcm-ex={round(meta['imSampRate'])},16s,{meta['nSavedChans']},le"
        )
        return [
            self.executable,
            "-y",
            raw_pcm,
            *options,
            str(bin_path),
            "-o",
            str(out_path),
        ]

    def decompress_command(
        self, compressed_path: Path, out_path: Path, options: list[str]
    ) -> list[str]:
        return [
            self.decoder,
            "-y",
            "--raw",
            *options,
            str(compressed_path),
            "-o",
            str(out_path),
        ]

    def verify_command(
        self, compressed_path: Path, options: list[str]
    ) -> list[str] | None:
        return [self.decoder, "-v", *options, str(compressed_path)]


BACKENDS = {"wavpack": WavPackBackend}


def get_backend(config: dict, name: str | None = None) -> tuple[Backend, dict]:
    """Build the backend named in the config (or overridden) and return it with its options."""
    backend_config = config.get("backend", {})
    name = name or backend_config.get("name", "wavpack")
    if name not in BACKENDS:
        raise ValueError(
            f"Unknown backend {name!r}, expected one of {sorted(BACKENDS)}!"
        )

    options = backend_config.get(name, {})
    executables = {
        key: value
        for key, value in options.items()
        if key in ("executable", "decoder")
    }

    return BACKENDS[name](**executables), options


def get_options(backend: Backend, options: dict, key: str) -> list[str]:
    """Options for one operation, falling back to the backend's defaults."""
    return list(options.get(key, getattr(backend, f"default_{key}", [])))
