from datetime import datetime
from pathlib import Path

import pandas as pd

from npx_compress.sglx_meta import SGLX_COLUMNS

PACK_MANIFEST_NAME = "npx_pack.manifest"
UNPACK_MANIFEST_NAME = "npx_unpack.manifest"

PACK_COLUMNS = (*SGLX_COLUMNS, "compressedFile", "compressionRatio", "compressedAt")
UNPACK_COLUMNS = ("compressedFile", "outputFile", "decompressedAt")


def get_manifest_path(manifest_dir: str | Path, name: str) -> Path:
    return Path(manifest_dir) / name


def read_manifest(manifest_path: str | Path, columns: tuple[str, ...]) -> pd.DataFrame:
    """Read a manifest, or return an empty frame if it doesn't exist yet."""
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return pd.DataFrame(columns=list(columns))

    return pd.read_csv(manifest_path)


def update_manifest(
    manifest_path: str | Path,
    rows: pd.DataFrame,
    columns: tuple[str, ...],
    key_column: str,
) -> pd.DataFrame:
    """Add rows to a manifest, replacing any existing entry for the same file."""
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = read_manifest(manifest_path, columns)
    manifest = manifest[~manifest[key_column].isin(rows[key_column])]
    manifest = pd.concat([manifest, rows], ignore_index=True)[list(columns)]
    manifest.to_csv(manifest_path, index=False)

    return manifest


def completed_inputs(
    manifest: pd.DataFrame, input_column: str, output_column: str
) -> set[Path]:
    """Inputs already processed, ignoring rows whose output no longer exists."""
    return {
        Path(input_file).resolve()
        for input_file, output_file in zip(
            manifest[input_column], manifest[output_column]
        )
        if Path(output_file).exists()
    }


def build_pack_rows(meta: pd.DataFrame, compressed_paths: list[Path]) -> pd.DataFrame:
    """Add the compression fields to the meta rows of the files just compressed."""
    rows = meta.copy()
    rows["compressedFile"] = [str(Path(p).resolve()) for p in compressed_paths]
    rows["compressionRatio"] = rows["fileSizeBytes"] / [
        Path(p).stat().st_size for p in compressed_paths
    ]
    rows["compressedAt"] = timestamp()

    return rows


def build_unpack_rows(
    compressed_paths: list[Path], output_paths: list[Path]
) -> pd.DataFrame:
    """Build the manifest rows for the files just decompressed."""
    return pd.DataFrame(
        {
            "compressedFile": [str(Path(p).resolve()) for p in compressed_paths],
            "outputFile": [str(Path(p).resolve()) for p in output_paths],
            "decompressedAt": timestamp(),
        }
    )


def timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
