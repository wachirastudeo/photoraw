import json
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".rawmini_projects"
DEFAULT_PROJECT = DEFAULT_ROOT / "default"

def _catalog_path(project_dir: Path | None = None) -> Path:
    proj = Path(project_dir) if project_dir else DEFAULT_PROJECT
    proj.mkdir(parents=True, exist_ok=True)
    return proj / "catalog.json"

def load_catalog(project_dir: Path | None = None):
    path = _catalog_path(project_dir)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_catalog(catalog: dict, project_dir: Path | None = None):
    try:
        path = _catalog_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_catalog error:", e)
