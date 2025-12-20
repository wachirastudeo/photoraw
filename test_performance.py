"""
Performance test suite for Ninlab optimizations
Tests memory usage and speed improvements
"""
import time
import numpy as np
from imaging import clamp01, apply_denoise, apply_film_grain, pipeline, DEFAULTS

print("=" * 60)
print("NINLAB PERFORMANCE TESTS")
print("=" * 60)

# Test 1: clamp01 in-place behavior
print("\n[Test 1] clamp01 in-place optimization")
arr = np.random.rand(4000, 6000, 3).astype(np.float32)
arr_id_before = id(arr)
result = clamp01(arr)
arr_id_after = id(result)

if arr.flags.owndata:
    # Should be in-place if owns data
    assert id(result) == arr_id_before, "clamp01 should modify in-place when possible"
    print("✓ clamp01 modifies in-place correctly")
else:
    print("✓ clamp01 creates copy for non-owned data (safe)")

# Test 2: Denoise speed
print("\n[Test 2] Denoise performance")
rgb = np.random.rand(2000, 3000, 3).astype(np.float32)

start = time.time()
result = apply_denoise(rgb, amount=0.5)
elapsed = time.time() - start

print(f"  Denoise time (6MP image, amount=0.5): {elapsed:.3f}s")
if elapsed < 2.5:
    print(f"  ✓ PASS - Faster than 2.5s baseline")
else:
    print(f"  ⚠ SLOW - Expected < 2.5s")

# Test 3: Film grain speed
print("\n[Test 3] Film grain performance")
rgb = np.random.rand(2000, 3000, 3).astype(np.float32)

start = time.time()
result = apply_film_grain(rgb, amount=0.3, size=0.5, roughness=0.5)
elapsed = time.time() - start

print(f"  Film grain time (6MP image): {elapsed:.3f}s")
if elapsed < 0.8:
    print(f"  ✓ PASS - Faster than 0.8s baseline")
else:
    print(f"  ⚠ SLOW - Expected < 0.8s")

# Test 4: Full pipeline speed (fast mode)
print("\n[Test 4] Pipeline performance (fast mode)")
rgb = np.random.rand(2000, 3000, 3).astype(np.float32)
adj = DEFAULTS.copy()
adj.update({
    "exposure": 0.5,
    "contrast": 0.2,
    "saturation": 0.3,
    "clarity": 0.1,
    "vignette": 0.2
})

start = time.time()
result = pipeline(rgb, adj, fast_mode=True)
elapsed = time.time() - start

print(f"  Pipeline (fast) time (6MP image): {elapsed:.3f}s")
if elapsed < 1.5:
    print(f"  ✓ PASS - Faster than 1.5s baseline")
else:
    print(f"  ⚠ SLOW - Expected < 1.5s")

# Test 5: Full pipeline speed (full quality)
print("\n[Test 5] Pipeline performance (full quality)")
start = time.time()
result = pipeline(rgb, adj, fast_mode=False)
elapsed = time.time() - start

print(f"  Pipeline (full) time (6MP image): {elapsed:.3f}s")
if elapsed < 4.0:
    print(f"  ✓ PASS - Faster than 4.0s baseline")
else:
    print(f"  ⚠ SLOW - Expected < 4.0s")

# Test 6: Memory efficiency
print("\n[Test 6] Memory efficiency check")
print("  Testing pipeline memory usage...")
import tracemalloc

tracemalloc.start()
rgb = np.random.rand(3000, 4500, 3).astype(np.float32)  # ~12MP
adj = DEFAULTS.copy()
adj.update({"exposure": 0.3, "contrast": 0.1})

current_before, peak_before = tracemalloc.get_traced_memory()
result = pipeline(rgb, adj, fast_mode=True)
current_after, peak_after = tracemalloc.get_traced_memory()
tracemalloc.stop()

peak_mb = (peak_after - peak_before) / 1024 / 1024
print(f"  Peak memory increase: {peak_mb:.1f} MB")
if peak_mb < 300:  # Should be reasonable for 12MP processing
    print(f"  ✓ PASS - Memory usage is efficient")
else:
    print(f"  ⚠ HIGH - Memory usage could be optimized further")

print("\n" + "=" * 60)
print("ALL TESTS COMPLETED")
print("=" * 60)
