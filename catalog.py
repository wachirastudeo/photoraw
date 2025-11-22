import json
from pathlib import Path
from datetime import datetime

DEFAULT_ROOT = Path.home() / ".rawmini_projects"
DEFAULT_PROJECT = DEFAULT_ROOT / "default"

def _catalog_path(project_dir: Path | None = None) -> Path:
    proj = Path(project_dir) if project_dir else DEFAULT_PROJECT
    proj.mkdir(parents=True, exist_ok=True)
    return proj / "catalog.json"

def _meta_path() -> Path:
    DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
    return DEFAULT_ROOT / "_meta.json"

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

def load_projects_meta():
    """Load project metadata including names and last used timestamps"""
    path = _meta_path()
    data = {"last_project": None, "projects": {}}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
            
    # Ensure structure is valid for legacy files
    if "projects" not in data:
        data["projects"] = {}
        
    return data

def save_projects_meta(meta: dict):
    """Save project metadata"""
    try:
        path = _meta_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_projects_meta error:", e)

def update_project_info(project_path: Path, display_name: str = None):
    """Update project information in metadata"""
    meta = load_projects_meta()
    proj_str = str(project_path.resolve())
    
    if proj_str not in meta["projects"]:
        meta["projects"][proj_str] = {}
    
    if display_name:
        meta["projects"][proj_str]["display_name"] = display_name
    
    meta["projects"][proj_str]["last_used"] = datetime.now().isoformat()
    meta["last_project"] = proj_str
    
    save_projects_meta(meta)
    return meta

def load_global_presets():
    """Load global presets from _meta.json"""
    meta = load_projects_meta()
    return meta.get("presets", {})

def save_global_presets(presets: dict):
    """Save global presets to _meta.json"""
    meta = load_projects_meta()
    meta["presets"] = presets
    save_projects_meta(meta)
