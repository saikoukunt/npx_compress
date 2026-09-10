from pathlib import Path


def find_files(
    input_paths: list[str | Path],
    file_extension: str,
    completed: set[Path] | None = None,
    override: bool = False,
    include_strings: list[str] | None = None,
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

    if include_strings:
        files = {f for f in files if matches_any(f, include_strings)}

    if completed and not override:
        files -= completed

    return sorted(files)


def matches_any(file: Path, include_strings: list[str]) -> bool:
    """Substrings are matched against the whole path, not just the file name."""
    return any(string in str(file) for string in include_strings)


def find_files_in_dir(input_path: Path, file_extension: str):
    suffix = file_extension if file_extension.startswith(".") else f".{file_extension}"
    return sorted(p for p in input_path.rglob(f"*{suffix}") if p.is_file())


def resolve_output_path(
    file: Path,
    input_paths: list[str | Path],
    output_dir: str | Path | None,
    extension: str,
) -> Path:
    """Where a processed file should be written, mirroring the input tree if asked to."""
    if output_dir is None:
        return file.with_suffix(extension)

    out_path = (
        Path(output_dir).resolve()
        / path_within_input_tree(file, input_paths).with_suffix(extension)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    return out_path


def path_within_input_tree(file: Path, input_paths: list[str | Path]) -> Path:
    """The file's path relative to the deepest input folder holding it, or its name."""
    input_dirs = sorted(
        (Path(p).resolve() for p in input_paths if Path(p).is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    )

    return next(
        (file.relative_to(d) for d in input_dirs if d in file.parents), Path(file.name)
    )


def convert_bin_path_to_meta(bin_path: str | Path) -> Path:
    """Swap the final extension of a SpikeGLX binary path for `.meta`."""
    return Path(bin_path).with_suffix(".meta")
