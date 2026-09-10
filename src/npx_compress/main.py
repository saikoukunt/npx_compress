from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import typer

from npx_compress.backends import Backend, get_backend, get_options
from npx_compress.config import load_config
from npx_compress.manifest import (
    PACK_COLUMNS,
    PACK_MANIFEST_NAME,
    UNPACK_COLUMNS,
    UNPACK_MANIFEST_NAME,
    build_pack_rows,
    build_unpack_rows,
    completed_inputs,
    get_manifest_path,
    read_manifest,
    update_manifest,
)
from npx_compress.path_utils import find_files, resolve_output_path
from npx_compress.sglx_meta import copy_meta_file, read_sglx_meta_files
from npx_compress.subprocess import (
    BackendError,
    is_oom,
    output_matches_file,
    run_backend,
)

app = typer.Typer()

PASSING_OUTCOMES = ("ok", "crc only")


@dataclass
class AppContext:
    manifest_dir: str
    backend: Backend
    backend_options: dict


@app.command()
def pack(
    context: typer.Context,
    input_paths: list[str] = typer.Argument(
        None, help="Paths to folders or files with data to be compressed"
    ),
    file_extension: str = typer.Option(
        "ap.bin", "-f", "--file-ext", help="file extension for recording binaries"
    ),
    output_dir: str = typer.Option(
        None, "--output-dir", help="write next to the input files if not given"
    ),
    override: bool = typer.Option(
        False, "-o", "--override", help="compress files even if already in the manifest"
    ),
    verify: bool = typer.Option(
        False, help="check each compressed file before recording it in the manifest"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="list the files that would be compressed and stop"
    ),
    include_strings: list[str] = typer.Option(
        None,
        "--include-string",
        help="only process files whose path contains one of these strings",
    ),
):
    app_context: AppContext = context.obj
    backend = app_context.backend
    options = get_options(backend, app_context.backend_options, "compress_options")

    input_paths = check_input_paths(input_paths)
    manifest_path = get_manifest_path(app_context.manifest_dir, PACK_MANIFEST_NAME)
    manifest = read_manifest(manifest_path, PACK_COLUMNS)

    files = find_files(
        input_paths,
        file_extension,
        completed_inputs(manifest, "binFile", "compressedFile"),
        override,
        include_strings,
    )
    if not files:
        print("No files to compress.", flush=True)
        return

    meta = read_sglx_meta_files(files)
    report_files("compress", files, meta)
    if dry_run:
        return

    packed, failed = [], []
    for row, file in zip(meta.index, files):
        out_path = resolve_output_path(file, input_paths, output_dir, backend.extension)
        try:
            run_backend(
                backend.compress_command(file, out_path, meta.loc[row], options)
            )
            if verify:
                verify_file(backend, out_path, app_context.backend_options)
        except BackendError as error:
            report_failure(file, error)
            failed.append(file)
            continue

        copy_meta_file(file, out_path)
        update_manifest(
            manifest_path,
            build_pack_rows(meta.loc[[row]], [out_path]),
            PACK_COLUMNS,
            "binFile",
        )
        packed.append(file)
        print(f"{file.name} -> {out_path.name}", flush=True)

    report_summary("compressed", packed, failed)


@app.command()
def verify(
    context: typer.Context,
    input_paths: list[str] = typer.Argument(
        None, help="Only check manifest entries under these paths"
    ),
    include_strings: list[str] = typer.Option(
        None,
        "--include-string",
        help="only check files whose path contains one of these strings",
    ),
):
    """Decompress each packed file and compare it byte for byte with the original."""
    app_context: AppContext = context.obj
    backend = app_context.backend
    options = get_options(backend, app_context.backend_options, "decompress_options")

    manifest_path = get_manifest_path(app_context.manifest_dir, PACK_MANIFEST_NAME)
    manifest = select_manifest_rows(
        read_manifest(manifest_path, PACK_COLUMNS), input_paths, include_strings
    )
    if manifest.empty:
        print("No packed files to check.", flush=True)
        return

    passed, failed = [], []
    for bin_file, compressed_file in zip(
        manifest["binFile"], manifest["compressedFile"]
    ):
        compressed_path = Path(compressed_file)
        outcome = check_roundtrip(
            backend, Path(bin_file), compressed_path, options, app_context
        )
        print(f"{outcome:<12}{compressed_path}", flush=True)
        (passed if outcome in PASSING_OUTCOMES else failed).append(compressed_path)

    print(f"{len(passed)} file(s) passed, {len(failed)} failed.", flush=True)
    for file in failed:
        print(f"  failed: {file}", flush=True)

    if failed:
        raise typer.Exit(1)


def check_roundtrip(
    backend: Backend,
    bin_path: Path,
    compressed_path: Path,
    options: list[str],
    app_context: AppContext,
) -> str:
    """Compare one compressed file with its original, falling back to a CRC check."""
    if not compressed_path.exists():
        return "MISSING"

    if not bin_path.exists():
        try:
            verify_file(backend, compressed_path, app_context.backend_options)
        except BackendError:
            return "CRC FAILED"

        return "crc only"

    command = backend.decompress_command(compressed_path, Path("-"), options)

    return "ok" if output_matches_file(command, bin_path) else "MISMATCH"


def select_manifest_rows(
    manifest: pd.DataFrame,
    input_paths: list[str] | None,
    include_strings: list[str] | None,
) -> pd.DataFrame:
    """Narrow the manifest the same way find_files narrows a directory tree."""
    if input_paths:
        roots = [str(Path(p).resolve()) for p in input_paths]
        manifest = manifest[
            manifest["binFile"].apply(lambda f: any(f.startswith(r) for r in roots))
        ]

    if include_strings:
        manifest = manifest[
            manifest["binFile"].apply(
                lambda f: any(string in f for string in include_strings)
            )
        ]

    return manifest


@app.command()
def unpack(
    context: typer.Context,
    input_paths: list[str] = typer.Argument(
        None, help="Paths to folders or files with data to be uncompressed"
    ),
    file_extension: str = typer.Option(
        ".wv", "-f", "--file-ext", help="file extension for compressed files"
    ),
    output_dir: str = typer.Option(
        None, "--output-dir", help="write next to the input files if not given"
    ),
    override: bool = typer.Option(
        False, "-o", "--override", help="expand files even if already in the manifest"
    ),
    verify: bool = typer.Option(
        False, help="check each compressed file before decompressing it"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="list the files that would be decompressed and stop"
    ),
    include_strings: list[str] = typer.Option(
        None,
        "--include-string",
        help="only process files whose path contains one of these strings",
    ),
):
    app_context: AppContext = context.obj
    backend = app_context.backend
    options = get_options(backend, app_context.backend_options, "decompress_options")

    input_paths = check_input_paths(input_paths)
    manifest_path = get_manifest_path(app_context.manifest_dir, UNPACK_MANIFEST_NAME)
    manifest = read_manifest(manifest_path, UNPACK_COLUMNS)

    files = find_files(
        input_paths,
        file_extension,
        completed_inputs(manifest, "compressedFile", "outputFile"),
        override,
        include_strings,
    )
    if not files:
        print("No files to decompress.", flush=True)
        return

    report_files("decompress", files, read_meta_if_present(files))
    if dry_run:
        return

    unpacked, failed = [], []
    for file in files:
        out_path = resolve_output_path(file, input_paths, output_dir, ".bin")
        try:
            if verify:
                verify_file(backend, file, app_context.backend_options)
            run_backend(backend.decompress_command(file, out_path, options))
        except BackendError as error:
            report_failure(file, error)
            failed.append(file)
            continue

        update_manifest(
            manifest_path,
            build_unpack_rows([file], [out_path]),
            UNPACK_COLUMNS,
            "compressedFile",
        )
        unpacked.append(file)
        print(f"{file.name} -> {out_path.name}", flush=True)

    report_summary("decompressed", unpacked, failed)


def verify_file(backend: Backend, compressed_path: Path, backend_options: dict) -> None:
    """Run the backend's integrity check, if it has one."""
    command = backend.verify_command(
        compressed_path, get_options(backend, backend_options, "verify_options")
    )
    if command:
        run_backend(command)


def report_files(verb: str, files: list[Path], meta: pd.DataFrame | None) -> None:
    """List the files a run will work on, before touching any of them."""
    print(file_table_header(meta is not None), flush=True)
    total = 0
    for position, file in enumerate(files):
        size = file.stat().st_size
        total += size
        print(
            f"{format_size(size):>10}  {describe_recording(meta, position)}{file}",
            flush=True,
        )

    print(f"{len(files)} file(s) to {verb}, {format_size(total)} total.", flush=True)


def file_table_header(with_meta: bool) -> str:
    columns = f"{'SIZE':>10}  "
    if with_meta:
        columns += f"{'CHANS':>7}  {'PROBE':<20}  {'LENGTH':<8}  "

    return columns + "FILE"


def describe_recording(meta: pd.DataFrame | None, position: int) -> str:
    """The meta fields worth seeing before a run, or nothing if the meta file is missing."""
    if meta is None:
        return ""

    row = meta.iloc[position]

    return f"{row['nSavedChans']:>4} ch  {row['probeType']:<20}  {row['recordingTime']}  "


def read_meta_if_present(files: list[Path]) -> pd.DataFrame | None:
    """Compressed files only have a meta file beside them if they were packed in place."""
    try:
        return read_sglx_meta_files(files)
    except FileNotFoundError:
        return None


def format_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024


def report_failure(file: Path, error: BackendError) -> None:
    """Report a failed file, or give up entirely if the backend ran out of memory."""
    if is_oom(error):
        raise SystemExit(f"{file.name}: backend ran out of memory, stopping.\n{error}")

    print(f"{file.name}: {error}", flush=True)


def report_summary(verb: str, succeeded: list, failed: list[Path]) -> None:
    print(f"{len(succeeded)} file(s) {verb}, {len(failed)} failed.", flush=True)
    for file in failed:
        print(f"  failed: {file}", flush=True)


def build_app_context(
    config: dict, manifest_dir: str | None, backend_name: str | None
) -> AppContext:
    """Resolve the callback's own options, which are parsed before default_map is set."""
    backend, backend_options = get_backend(config, backend_name)

    return AppContext(
        manifest_dir=manifest_dir or config.get("manifest_dir", "."),
        backend=backend,
        backend_options=backend_options,
    )


def check_input_paths(input_paths: list[str] | None) -> list[str]:
    """Input paths are optional on the CLI so they can come from the config file."""
    if not input_paths:
        raise typer.BadParameter(
            "No input paths given on the command line or in the config file"
        )

    return input_paths


@app.callback()
def main(
    context: typer.Context,
    config_path: str = typer.Option(None, help="Path to config .toml file"),
    manifest_dir: str = typer.Option(
        None, "--manifest-dir", help="Directory holding the pack/unpack manifests"
    ),
    backend_name: str = typer.Option(
        None, "--backend", help="Compression backend, overrides the config file"
    ),
):
    config = load_config(Path(config_path) if config_path else None)
    context.default_map = config
    context.obj = build_app_context(config, manifest_dir, backend_name)


if __name__ == "__main__":
    app()
