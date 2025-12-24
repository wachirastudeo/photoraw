"""
Preview Cache Manager

Handles disk-based caching of decoded preview images and thumbnails
to speed up subsequent application launches.
"""

import os
import hashlib
import numpy as np
from pathlib import Path
import time

# Cache directory
CACHE_DIR = Path.home() / ".ninlab_cache" / "previews"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_cache_key(file_path):
    """Generate cache key from file path using MD5 hash"""
    return hashlib.md5(str(file_path).encode('utf-8')).hexdigest()

def get_cache_path(file_path):
    """Get the cache file path for a given source file"""
    cache_key = get_cache_key(file_path)
    return CACHE_DIR / f"{cache_key}.npz"

def is_cache_valid(file_path, cache_path):
    """
    Check if cache is valid by comparing modification times
    Returns True if cache exists and is newer than source file
    """
    if not cache_path.exists():
        return False
    
    try:
        source_mtime = os.path.getmtime(file_path)
        cache_mtime = os.path.getmtime(cache_path)
        
        # Cache is valid if it's newer than source
        return cache_mtime >= source_mtime
    except (OSError, FileNotFoundError):
        return False

def save_to_cache(file_path, full_array, thumb_array):
    """
    Save decoded arrays to cache
    
    Args:
        file_path: Path to original image file
        full_array: Full preview numpy array
        thumb_array: Thumbnail numpy array
    """
    try:
        cache_path = get_cache_path(file_path)
        
        # Get source file modification time
        source_mtime = os.path.getmtime(file_path)
        
        # Save arrays with metadata
        np.savez_compressed(
            cache_path,
            full=full_array,
            thumb=thumb_array,
            mtime=source_mtime
        )
        
        # Set cache file mtime to match source for easier validation
        os.utime(cache_path, (source_mtime, source_mtime))
        
    except Exception as e:
        # Silently fail - cache is optional
        print(f"Cache save failed for {file_path}: {e}")
        pass

def load_from_cache(file_path):
    """
    Load cached arrays if valid
    
    Returns:
        dict with 'full' and 'thumb' keys, or None if cache invalid/missing
    """
    try:
        cache_path = get_cache_path(file_path)
        
        # Check if cache is valid
        if not is_cache_valid(file_path, cache_path):
            return None
        
        # Load cache
        data = np.load(cache_path)
        
        return {
            'full': data['full'],
            'thumb': data['thumb']
        }
        
    except Exception as e:
        # Cache miss or corrupted - will re-decode
        return None

def clear_old_cache(max_age_days=30):
    """
    Remove cache files older than max_age_days
    
    Args:
        max_age_days: Maximum age in days before cache is deleted
    """
    try:
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        
        removed_count = 0
        removed_size = 0
        
        for cache_file in CACHE_DIR.glob("*.npz"):
            try:
                if cache_file.stat().st_mtime < cutoff_time:
                    size = cache_file.stat().st_size
                    cache_file.unlink()
                    removed_count += 1
                    removed_size += size
            except Exception:
                continue
        
        if removed_count > 0:
            size_mb = removed_size / (1024 * 1024)
            print(f"Cache cleanup: Removed {removed_count} files ({size_mb:.1f} MB)")
            
    except Exception as e:
        print(f"Cache cleanup failed: {e}")

def get_cache_stats():
    """Get cache statistics"""
    try:
        total_size = 0
        file_count = 0
        
        for cache_file in CACHE_DIR.glob("*.npz"):
            try:
                total_size += cache_file.stat().st_size
                file_count += 1
            except Exception:
                continue
        
        return {
            'file_count': file_count,
            'total_size_mb': total_size / (1024 * 1024),
            'cache_dir': str(CACHE_DIR)
        }
    except Exception:
        return {'file_count': 0, 'total_size_mb': 0, 'cache_dir': str(CACHE_DIR)}
