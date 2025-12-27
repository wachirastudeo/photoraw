"""
Clear image cache to force re-decode with correct orientation
"""
import shutil
from pathlib import Path

cache_dir = Path.home() / ".ninlab_cache" / "previews"

if cache_dir.exists():
    try:
        shutil.rmtree(cache_dir)
        print(f"✅ Cache cleared: {cache_dir}")
        print("   Restart the app to reload images with correct orientation")
    except Exception as e:
        print(f"❌ Failed to clear cache: {e}")
else:
    print(f"ℹ️  Cache directory doesn't exist: {cache_dir}")
