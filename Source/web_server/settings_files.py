import json
from pathlib import Path
from typing import Any


SETTINGS_DIR = (Path(__file__).resolve().parent / "data" / "settings").resolve()


def get_settings_path(file_name: str) -> Path:
    path = (SETTINGS_DIR / file_name).resolve()
    if SETTINGS_DIR not in path.parents:
        raise ValueError(f"Invalid settings path: {file_name}")
    return path


def read_settings_json(file_name: str) -> dict[str, Any]:
    with get_settings_path(file_name).open("r", encoding="utf-8") as file:
        result = json.load(file)
    assert isinstance(result, dict)
    return result


def find_settings_file(pattern: str) -> Path:
    matches = sorted(SETTINGS_DIR.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No settings file matching {pattern!r} in {SETTINGS_DIR}",
        )
    return matches[0]


def read_settings_bytes(file_name: str) -> bytes:
    return get_settings_path(file_name).read_bytes()


def read_matching_settings_bytes(pattern: str) -> tuple[Path, bytes]:
    path = find_settings_file(pattern)
    return (path, path.read_bytes())
