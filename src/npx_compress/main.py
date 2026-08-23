from pathlib import Path

import typer

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
from npx_compress.path_utils import find_files
from npx_compress.sglx_meta import read_sglx_meta_files

app = typer.Typer()


@app.command()
def pack(
    context: typer.Context,
    input_paths: list[str] = typer.Argument(
        None, help="Paths to folders or files with data to be compressed"
    ),
    file_extension: str = typer.Option(
        "ap.bin", "-f", "--file-ext", help="file extension for recording binaries"
    ),
    override: bool = typer.Option(
        False, "-o", "--override", help="compress files even if already in the manifest"
    ),
):
    input_paths = check_input_paths(input_paths)
    manifest_path = get_manifest_path(context.obj, PACK_MANIFEST_NAME)
    manifest = read_manifest(manifest_path, PACK_COLUMNS)

    files = find_files(
        input_paths,
        file_extension,
        completed_inputs(manifest, "binFile", "compressedFile"),
        override,
    )
    if not files:
        print("No files to compress.")
        return

    meta = read_sglx_meta_files(files)

    # TODO: compress each file and collect the paths written
    compressed_paths = []
    if not compressed_paths:
        return

    update_manifest(
        manifest_path, build_pack_rows(meta, compressed_paths), PACK_COLUMNS, "binFile"
    )


@app.command()
def unpack(
    context: typer.Context,
    input_paths: list[str] = typer.Argument(
        None, help="Paths to folders or files with data to be uncompressed"
    ),
    file_extension: str = typer.Option(
        ".wv", "-f", "--file-ext", help="file extension for compressed files"
    ),
    override: bool = typer.Option(
        False, "-o", "--override", help="expand files even if already in the manifest"
    ),
):
    input_paths = check_input_paths(input_paths)
    manifest_path = get_manifest_path(context.obj, UNPACK_MANIFEST_NAME)
    manifest = read_manifest(manifest_path, UNPACK_COLUMNS)

    files = find_files(
        input_paths,
        file_extension,
        completed_inputs(manifest, "compressedFile", "outputFile"),
        override,
    )
    if not files:
        print("No files to decompress.")
        return

    # TODO: decompress each file and collect the paths written
    output_paths = []
    if not output_paths:
        return

    update_manifest(
        manifest_path,
        build_unpack_rows(files, output_paths),
        UNPACK_COLUMNS,
        "compressedFile",
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
):
    config = load_config(Path(config_path) if config_path else None)
    context.default_map = config
    # the callback's own options are parsed before default_map is set, so the config
    # value for manifest_dir has to be applied by hand
    context.obj = manifest_dir or config.get("manifest_dir", ".")


if __name__ == "__main__":
    app()
