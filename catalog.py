import json
from pathlib import Path

CATALOG_PATH = Path.home() / ".rawmini_catalog.json"

def load_catalog():
    if CATALOG_PATH.exists():
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_catalog(catalog: dict):
    try:
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_catalog error:", e)
