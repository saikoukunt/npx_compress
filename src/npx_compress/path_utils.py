from pathlib import Path


def find_files(
    input_paths: list[str | Path],
    file_extension: str,
    completed: set[Path] | None = None,
    override: bool = False,
) -> list[Path]:
    """Find files to process, skipping ones already recorded in a manifest."""
    files = set()
    for input_path in input_paths:
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input path {str(input_path)} doesn't exist!")

        if input_path.is_file():
            files.add(input_path.resolve())
        else:
            files.update(p.resolve() for p in find_files_in_dir(input_path, file_extension))

    if completed and not override:
        files -= completed

    return sorted(files)


def find_files_in_dir(input_path: Path, file_extension: str):
    suffix = file_extension if file_extension.startswith(".") else f".{file_extension}"
    return sorted(p for p in input_path.rglob(f"*{suffix}") if p.is_file())


def convert_bin_path_to_meta(bin_path: str | Path) -> Path:
    """Swap the final extension of a SpikeGLX binary path for `.meta`."""
    return Path(bin_path).with_suffix(".meta")
