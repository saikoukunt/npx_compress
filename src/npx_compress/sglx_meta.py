from pathlib import Path

import pandas as pd

from npx_compress.path_utils import convert_bin_path_to_meta

# imDatPrb_type values, https://billkarsh.github.io/SpikeGLX/Sgl_help/Metadata_Help.html
PROBE_TYPES = {
    "0": "NP1.0",
    "21": "NP2.0 (1-shank)",
    "24": "NP2.0 (4-shank)",
}

# meta keys we read
META_FIELDS = ("nSavedChans", "imSampRate", "fileTimeSecs", "fileSizeBytes")

# columns of the frames returned below, in order
SGLX_COLUMNS = ("binFile", *META_FIELDS, "probeType", "recordingTime")


def read_sglx_meta_files(bin_paths: list[str | Path]) -> pd.DataFrame:
    """Load the meta fields for several SpikeGLX binaries into one DataFrame."""
    metas = [read_sglx_meta_file(bin_path) for bin_path in bin_paths]
    if not metas:
        raise ValueError("No binary files given!")

    return pd.concat(metas, ignore_index=True)


def read_sglx_meta_file(bin_path: str | Path) -> pd.DataFrame:
    """Load the fields of interest from a meta file into a one-row DataFrame."""
    meta_path = convert_bin_path_to_meta(bin_path)
    if not meta_path.exists():
        raise FileNotFoundError(f"Meta file {str(meta_path)} doesn't exist!")

    raw = {}
    for line in meta_path.read_text().splitlines():
        key, _, value = line.partition("=")
        raw[key.strip()] = value.strip()

    fields = {"binFile": str(Path(bin_path).resolve())}
    fields.update({key: raw[key] for key in META_FIELDS if key in raw})
    fields["probeType"] = get_probe_type(raw)

    missing = set(META_FIELDS) - fields.keys()
    if missing:
        raise KeyError(f"Meta file {str(meta_path)} is missing {sorted(missing)}!")

    fields["recordingTime"] = format_duration(float(fields["fileTimeSecs"]))

    return pd.DataFrame([fields])[list(SGLX_COLUMNS)].astype(
        {
            "nSavedChans": int,
            "imSampRate": float,
            "fileTimeSecs": float,
            "fileSizeBytes": int,
        }
    )


def get_probe_type(raw: dict[str, str]) -> str:
    """Resolve the probe type across meta file versions."""
    if "imDatPrb_type" in raw:
        code = raw["imDatPrb_type"]
        return PROBE_TYPES.get(code, f"unknown (imDatPrb_type={code})")
    if "imProbeOpt" in raw:  # phase3A probes predate imDatPrb_type
        return f"NP1.0 phase3A (option {raw['imProbeOpt']})"
    return "unknown"


def format_duration(seconds: float) -> str:
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
