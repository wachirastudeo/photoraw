
import numpy as np
import time
from imaging import process_image_fast, DEFAULTS

def test_fast_mode_logic():
    # Create a small blank image
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    
    # Use DEFAULTS as base to avoid KeyError
    adj = DEFAULTS.copy()
    adj.update({
        "denoise": 1.0,      # Heavy
        "grain_amount": 1.0, # Heavy
        "defringe": 1.0,     # Heavy
        "clarity": 1.0,      # Heavy
    })
    
    print("Testing Normal Mode (Slow)...")
    start = time.time()
    res_normal = process_image_fast(img, adj, fast_mode=False)
    t_normal = time.time() - start
    print(f"Normal Mode Time: {t_normal:.6f}s")
    
    print("Testing Fast Mode (Fast)...")
    start = time.time()
    res_fast = process_image_fast(img, adj, fast_mode=True)
    t_fast = time.time() - start
    print(f"Fast Mode Time: {t_fast:.6f}s")
    
    # Verification
    if np.array_equal(res_normal, res_fast):
        print("FAIL: Results are identical! Fast mode did not disable effects.")
    else:
        print("PASS: Results differ. Fast mode disabled some effects.")
        
    print("Test Complete.")

if __name__ == "__main__":
    test_fast_mode_logic()
