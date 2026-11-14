"""On-demand spaCy model downloader and local directory manager.

Downloads official spaCy model wheels directly from explosion/spacy-models
without invoking pip or sys.executable, so it works inside frozen
PyInstaller / Flet desktop binaries.
"""

import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile
import requests
import spacy

COMPATIBILITY_URL = (
    "https://raw.githubusercontent.com/explosion/spacy-models/master/compatibility.json"
)
WHEEL_URL_TEMPLATE = (
    "https://github.com/explosion/spacy-models/releases/download/"
    "{model}-{version}/{model}-{version}-py3-none-any.whl"
)

MODEL_CATALOG = {
    "en_core_web_sm": "en_core_web_sm (~12 MB, Fast)",
    "en_core_web_md": "en_core_web_md (~40 MB, Balanced)",
    "en_core_web_lg": "en_core_web_lg (~560 MB, High Accuracy)",
}

CONFIG_PATH = Path.home() / ".mmiwg_highlighter_config.json"


def get_default_models_dir() -> Path:
    """Return the default user-writable model storage directory."""
    return Path.home() / "Documents" / "MMIWG_Models"


def load_models_dir() -> Path:
    """Load the saved model directory from config, falling back to Documents/MMIWG_Models."""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            saved = data.get("models_dir")
            if saved:
                return Path(saved)
        except Exception:
            pass
    return get_default_models_dir()


def save_models_dir(models_dir: Path) -> None:
    """Persist the user's chosen model directory."""
    CONFIG_PATH.write_text(
        json.dumps({"models_dir": str(models_dir)}, indent=2),
        encoding="utf-8",
    )


def get_model_path(model_name: str, models_dir: Path) -> Path:
    """Return the expected local directory for an extracted spaCy model."""
    return Path(models_dir) / model_name


def is_model_installed(model_name: str, models_dir: Path) -> bool:
    """Check whether a spaCy model has been extracted into models_dir."""
    model_path = get_model_path(model_name, models_dir)
    return (model_path / "config.cfg").is_file() and (model_path / "meta.json").is_file()


def resolve_compatible_model_version(model_name: str) -> str:
    """Query spaCy's compatibility table for the installed spaCy major.minor version."""
    parts = spacy.__version__.split(".")
    spacy_mm = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else spacy.__version__

    resp = requests.get(COMPATIBILITY_URL, timeout=15)
    resp.raise_for_status()
    compat = resp.json()

    spacy_table = compat.get("spacy", {})
    versions = spacy_table.get(spacy_mm, {}).get(model_name, [])
    if versions:
        return versions[0]

    raise RuntimeError(
        f"No compatible version found for {model_name} with spaCy {spacy.__version__}."
    )


def download_and_install_model(
    model_name: str,
    models_dir: Path,
    progress_callback=None,
    status_callback=None,
) -> Path:
    """Download a spaCy model wheel and extract its model package into models_dir."""
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    target_dir = get_model_path(model_name, models_dir)

    if status_callback:
        status_callback(f"Checking compatible version for {model_name}...")
    version = resolve_compatible_model_version(model_name)
    wheel_url = WHEEL_URL_TEMPLATE.format(model=model_name, version=version)

    if status_callback:
        status_callback(f"Downloading {model_name} v{version}...")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".whl") as tmp_whl:
        tmp_whl_path = Path(tmp_whl.name)

    try:
        with requests.get(wheel_url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(tmp_whl_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 128):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(min(downloaded / total_size, 1.0))

        if status_callback:
            status_callback(f"Extracting {model_name} to {models_dir}...")

        with tempfile.TemporaryDirectory() as tmp_extract:
            with zipfile.ZipFile(tmp_whl_path, "r") as zf:
                zf.extractall(tmp_extract)

            # Standard spaCy wheel layout: <model_name>/<model_name>-<version>/config.cfg
            candidate = Path(tmp_extract) / model_name / f"{model_name}-{version}"
            if not (candidate / "config.cfg").is_file():
                # Fallback search in case of slightly different inner folder naming
                matches = list(Path(tmp_extract).rglob("config.cfg"))
                if not matches:
                    raise RuntimeError(f"Invalid model archive for {model_name}.")
                candidate = matches[0].parent

            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(candidate, target_dir)

        if not is_model_installed(model_name, models_dir):
            raise RuntimeError(f"Model installation verification failed at {target_dir}.")

        if progress_callback:
            progress_callback(1.0)
        if status_callback:
            status_callback(f"{model_name} ready!")
        return target_dir
    finally:
        if tmp_whl_path.exists():
            os.remove(tmp_whl_path)


def load_spacy_model(model_name: str, models_dir: Path):
    """Load an installed spaCy model from models_dir."""
    model_path = get_model_path(model_name, models_dir)
    if not is_model_installed(model_name, models_dir):
        raise FileNotFoundError(
            f"Model '{model_name}' is not installed in {models_dir}. Please download it first."
        )
    return spacy.load(str(model_path))
