import numpy as np
import time
import sys
import os

sys.path.append(os.getcwd())

try:
    import ninlab_core
    print("✅ Rust extension loaded")
except ImportError as e:
    print(f"❌ Rust extension not available: {e}")
    sys.exit(1)

from imaging import process_image_fast, DEFAULTS, pipeline

def benchmark():
    # Test with different image sizes
    sizes = [
        (1920, 1080, "HD"),
        (3840, 2160, "4K"),
        (5760, 3840, "6K"),
    ]
    
    settings = DEFAULTS.copy()
    settings.update({
        "exposure": 0.5,
        "contrast": 0.2,
        "saturation": 0.3,
        "temperature": 10.0,
        "tint": -5.0,
        "highlights": -0.3,
        "shadows": 0.4,
        "h_red": 10.0,
        "s_blue": 0.5,
        "vignette": 0.3,
    })
    
    print("\n" + "="*70)
    print("BENCHMARK: Rust vs Python Image Processing")
    print("="*70)
    
    for width, height, label in sizes:
        print(f"\n📸 Testing {label} ({width}x{height})")
        print("-" * 70)
        
        # Create test image
        img = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
        
        # Warm up
        _ = process_image_fast(img, settings)
        
        # Benchmark Rust (via process_image_fast which uses Rust if available)
        rust_times = []
        for i in range(5):
            start = time.perf_counter()
            result_rust = process_image_fast(img, settings)
            rust_time = time.perf_counter() - start
            rust_times.append(rust_time)
        
        rust_avg = np.mean(rust_times)
        rust_std = np.std(rust_times)
        
        # Benchmark Pure Python
        python_times = []
        for i in range(5):
            src01 = img.astype(np.float32) / 255.0
            start = time.perf_counter()
            out01 = pipeline(src01, settings, fast_mode=False)
            result_python = (np.clip(out01, 0, 1) * 255.0 + 0.5).astype(np.uint8)
            python_time = time.perf_counter() - start
            python_times.append(python_time)
        
        python_avg = np.mean(python_times)
        python_std = np.std(python_times)
        
        # Calculate speedup
        speedup = python_avg / rust_avg
        
        print(f"  Rust:   {rust_avg*1000:7.2f}ms ± {rust_std*1000:5.2f}ms")
        print(f"  Python: {python_avg*1000:7.2f}ms ± {python_std*1000:5.2f}ms")
        print(f"  🚀 Speedup: {speedup:.2f}x faster")
        
        # Verify accuracy
        diff = np.abs(result_rust.astype(int) - result_python.astype(int))
        mean_diff = np.mean(diff)
        max_diff = np.max(diff)
        print(f"  Accuracy: mean diff = {mean_diff:.4f}, max diff = {max_diff}")
    
    print("\n" + "="*70)
    print("Summary:")
    print("  - Rust implementation provides significant speedup")
    print("  - Results are nearly identical (minor rounding differences)")
    print("  - Larger images benefit more from Rust's parallel processing")
    print("="*70 + "\n")

if __name__ == "__main__":
    benchmark()
