import tomllib
from pathlib import Path

import typer


def load_config(path: Path | None = None):
    config_path = path or get_config_path()
    return tomllib.loads(config_path.read_text()) if config_path.exists() else {}


# TODO: implement a search hierarchy instead of this
def get_config_path():
    return Path(typer.get_app_dir("npx-compress")) / "config.toml"
