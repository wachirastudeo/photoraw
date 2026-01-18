
import numpy as np
import sys
import os

# Add project root to path
sys.path.append("/Users/pae/photoapp/photoraw")

try:
    from imaging import apply_tone_regions, clamp01
except ImportError:
    print("Could not import imaging.py. Make sure you are in the correct directory.")
    sys.exit(1)

def test_highlight_recovery():
    print("Testing Highlight Recovery Logic...")
    
    # Create a gradient from 0.0 to 2.0 (representing HDR data)
    # 0.5 is mid-grey, 1.0 is white, 2.0 is super-bright
    data = np.linspace(0.0, 2.0, 100).reshape(10, 10)
    # Make it 3 channels
    rgb = np.stack([data, data, data], axis=-1)
    
    # Test 1: Negative Highlight (Should Recover/Darken in new logic, Brighten in old)
    # In old logic: hi < 0 -> Boost -> Brightens
    # In new logic: hi < 0 -> Recover -> Darkens
    
    hi_val = -0.5
    res = apply_tone_regions(rgb.copy(), hi=hi_val)
    
    # Check what happened to super bright pixel (index 99, val 2.0)
    orig_val = rgb[9, 9, 0] # 2.0
    new_val = res[9, 9, 0]
    
    print(f"\nScanning Highlight = {hi_val}:")
    print(f"  Original Super-Bright (2.0): {orig_val:.4f}")
    print(f"  Result: {new_val:.4f}")
    
    if new_val < orig_val:
        print("  -> Result is DARKER (Recovery behavior - Desired for Negative)")
    else:
        print("  -> Result is BRIGHTER (Boost behavior - Old/Wrong for Negative)")

    # Test 2: Positive Highlight (Should Brighten/Boost in new logic, Darken in old)
    hi_val = 0.5
    res = apply_tone_regions(rgb.copy(), hi=hi_val)
    
    orig_val = rgb[9, 9, 0] # 2.0
    new_val = res[9, 9, 0]
    
    print(f"\nScanning Highlight = {hi_val}:")
    print(f"  Result: {new_val:.4f}")
    
    if new_val > orig_val:
        print("  -> Result is BRIGHTER (Boost behavior - Desired for Positive)")
    else:
        print("  -> Result is DARKER (Compression behavior - Old/Wrong for Positive)")

    # Check for Solarization (values wrapping around or acting weirdly)
    # In particular, check if values > 1.0 are handled gracefully without artifacts
    print("\nChecking for potential solarization/clipping issues...")
    if np.any(res < 0):
        print("  WARNING: Negative values detected!")
    
    print(f"  Max value: {np.max(res):.4f}")

    # Test 3: Color Shift / Desaturation Check
    print("\nChecking for Color Shift/Desaturation in Highlights...")
    # Create a bright saturated pixel (Skin tone-ish)
    # R=2.0, G=1.5, B=1.0 (Bright Orange/Skin)
    pixel = np.array([[[2.0, 1.5, 1.0]]]) # Shape (1,1,3)
    
    # Apply strong highlight recovery
    res_color = apply_tone_regions(pixel.copy(), hi=-1.0)
    
    r1, g1, b1 = pixel[0,0]
    r2, g2, b2 = res_color[0,0]
    
    # Check Ratios (Hue proxy)
    ratio_rg_1 = r1/g1 if g1 > 0 else 0
    ratio_rg_2 = r2/g2 if g2 > 0 else 0
    
    print(f"  Original: R={r1:.2f} G={g1:.2f} B={b1:.2f} (R/G ratio: {ratio_rg_1:.2f})")
    print(f"  Recovered: R={r2:.2f} G={g2:.2f} B={b2:.2f} (R/G ratio: {ratio_rg_2:.2f})")
    
    if abs(ratio_rg_1 - ratio_rg_2) > 0.1:
        print("  WARNING: Significant Hue/Ratio shift detected! (Causes 'grey' or 'muddy' look)")
    else:
        print("  Color ratios preserved.")


if __name__ == "__main__":
    test_highlight_recovery()
