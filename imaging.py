import os
import numpy as np
from PIL import Image

try:
    import rawpy
except Exception:
    rawpy = None

try:
    import ninlab_core
except ImportError:
    ninlab_core = None
    # Silently fall back to Python implementation

def clamp01(a):
    """Clamp array to [0, 1] range. In-place when safe."""
    # Only do in-place if array owns its data (not a view)
    if a.flags.owndata and a.flags.writeable:
        return np.clip(a, 0, 1, out=a)
    else:
        return np.clip(a, 0, 1)

# ค่าตั้งต้น (รวมทรานส์ฟอร์ม)
DEFAULTS = {
    "exposure":0.0,"contrast":0.0,"highlights":0.0,"shadows":0.0,"whites":0.0,"blacks":0.0,
    "saturation":0.0,"vibrance":0.0,"temperature":0.0,"tint":0.0,"gamma":1.0,
    "clarity":0.0,"texture":0.0,"mid_contrast":0.0,"dehaze":0.0,"denoise":0.0,
    "vignette":0.0,"defringe":0.0,"export_sharpen":0.2,"tone_curve":0.0,"curve_lut":None,
    "grain_amount":0.0,"grain_size":0.5,"grain_roughness":0.5,
    **{f"h_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    **{f"s_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    **{f"l_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    # transforms
    "angle": 0.0,           # หมุนแบบละเอียด (-10 ถึง +10 องศา สำหรับปรับภาพเอียง)
    "rotate": 0,            # หมุนองศา (0/90/180/270 แนะนำ)
    "flip_h": False,        # กลับซ้าย-ขวา
    "crop": None,           # dict {"x":..,"y":..,"w":..,"h":..} normalized [0..1] หรือ None
}

_COLORS = ["red","orange","yellow","green","aqua","blue","purple","magenta"]
_COLOR_CENTERS = {"red":0.0,"orange":30.0,"yellow":60.0,"green":120.0,"aqua":180.0,"blue":240.0,"purple":280.0,"magenta":320.0}
_COLOR_WIDTH = 50.0

def rgb_to_lum(rgb): 
    return 0.2126*rgb[...,0] + 0.7152*rgb[...,1] + 0.0722*rgb[...,2]

def apply_white_balance(rgb, temperature=0.0, tint=0.0):
    r = 1 + 0.8*temperature - 0.2*tint
    g = 1 - 0.1*temperature + 0.4*tint
    b = 1 - 0.8*temperature - 0.2*tint
    # Modify in-place using advanced indexing (creates view, then modifies)
    rgb = rgb.copy()  # Need copy to avoid modifying original
    rgb[..., 0] *= r
    rgb[..., 1] *= g
    rgb[..., 2] *= b
    return rgb

def auto_white_balance(rgb):
    """
    Calculate auto white balance corrections using Gray World algorithm.
    Returns (temperature, tint) adjustment values.
    """
    # Use middle 50% of luminance range to avoid clipped areas
    lum = rgb_to_lum(rgb)
    mask = (lum > 0.25) & (lum < 0.75)
    
    if not np.any(mask):
        # Fallback to all pixels if mask is empty
        mask = np.ones(lum.shape, dtype=bool)
    
    # Calculate average RGB in the valid range
    r_avg = np.mean(rgb[..., 0][mask])
    g_avg = np.mean(rgb[..., 1][mask])
    b_avg = np.mean(rgb[..., 2][mask])
    
    # Gray world: assume average should be neutral gray
    avg = (r_avg + g_avg + b_avg) / 3.0
    
    if avg < 1e-6:
        return 0.0, 0.0
    
    # Calculate how much to adjust each channel
    r_scale = avg / (r_avg + 1e-6)
    b_scale = avg / (b_avg + 1e-6)
    g_scale = avg / (g_avg + 1e-6)
    
    # Convert scale factors to temperature/tint
    # Temperature affects R-B balance
    # Tint affects G-M balance
    
    # Temperature: positive = warmer (more red), negative = cooler (more blue)
    # We need to map r_scale/b_scale to temperature range
    temp_raw = (r_scale - b_scale) / 2.0
    temperature = np.clip(temp_raw * 0.5, -1.0, 1.0)
    
    # Tint: positive = more green, negative = more magenta
    tint_raw = (g_scale - (r_scale + b_scale) / 2.0)
    tint = np.clip(tint_raw * 0.5, -1.0, 1.0)
    
    return float(temperature), float(tint)

def apply_tone_regions(rgb, hi=0.0, sh=0.0, wh=0.0, bl=0.0):
    # Skip if no adjustments
    if abs(hi) < 1e-6 and abs(sh) < 1e-6 and abs(wh) < 1e-6 and abs(bl) < 1e-6:
        # If no explicit tone mapping, we still need to compress HDR values > 1.0
        # Simple soft-clip for values > 1.0 (knee)
        if np.any(rgb > 1.0):
            return np.where(rgb > 1.0, 1.0 + np.log(np.maximum(rgb, 1e-10)), rgb) # basic reinhard-ish
        return rgb
    
    y = rgb_to_lum(rgb)
    
    # Better Shadow Recovery (Digging)
    if abs(sh) > 1e-6:
        # Create mask focused deeply on darks
        # Only affect pixels < 0.2 mostly, taper to 0.5
        shadow_mask = np.clip((0.5 - y) * 2.0, 0, 1) ** 2
        
        # Logarithmic lift for natural digging
        # If sh > 0, we want to multiply.
        lift = 1.0 + sh * 4.0 # Stronger range (up to 5x gain in deep shadows)
        
        # Apply more gain to darker areas
        rgb = rgb * (1.0 + (lift - 1.0) * shadow_mask[..., None])

    # Highlight Compression (HDR Pullback)
    if abs(hi) > 1e-6:
        # Mask for bright areas
        # Soft transition start at 0.7
        hi_mask = np.clip((y - 0.5) * 2.0, 0, 1) ** 2
        
        # Compression factor
        # compress = 1.0 / (1.0 + hi * 2.0)
        # rgb = rgb * (1.0 - hi_mask[..., None]) + (rgb * compress) * hi_mask[..., None]
        
        # New method: Compress HDR highlights (>1.0) back to 1.0 range
        # If hi=1.0, we aggressively map >1.0 to near 1.0
        if hi > 0:
            scale = 1.0 + hi * 3.0
            # RGB / Scale for highlights
            target = rgb / scale
            rgb = rgb * (1.0 - hi_mask[..., None]) + target * hi_mask[..., None]

    # Whites (Point shift)
    if abs(wh) > 1e-6:
        rgb = rgb * (1.0 + wh * 0.5)
    
    # Blacks (Offset)
    if abs(bl) > 1e-6:
        rgb = rgb + bl * 0.1

    return rgb # Return float, let later stages clamp

def apply_saturation_vibrance(rgb, saturation=0.0, vibrance=0.0):
    gray=rgb.mean(axis=2,keepdims=True)
    out=gray+(rgb-gray)*(1.0+saturation)
    if abs(vibrance)>1e-6:
        sat_now=np.maximum(np.abs(rgb-gray),1e-6).mean(axis=2,keepdims=True)
        weight=np.clip(1.0-sat_now*2.0,0,1)
        out=gray+(out-gray)*(1.0+vibrance*weight)
    return out

def apply_contrast_gamma(rgb, contrast=0.0, gamma=1.0):
    out=rgb
    if abs(contrast)>1e-6: out=0.5+(out-0.5)*(1.0+contrast)
    if abs(gamma-1.0)>1e-6: out=np.power(np.clip(out,0,1),1.0/gamma)
    return out
 
def apply_dehaze(rgb, amount=0.0):
    if abs(amount)<1e-6: return rgb
    y = clamp01(rgb_to_lum(rgb))[...,None]
    veil = y * (0.6*amount)
    base = clamp01(rgb - veil)
    return apply_contrast_gamma(base, contrast=0.4*amount, gamma=1.0)

def apply_denoise(rgb, amount=0.0):
    """Bilateral filtering for noise reduction with edge preservation"""
    if amount <= 1e-6:
        return rgb
    
    # Use scipy for faster Gaussian blur
    from scipy.ndimage import gaussian_filter
    
    # Fewer passes for better performance
    num_passes = max(1, int(amount * 1.5))  # Reduced from 2*amount
    result = rgb.copy()
    
    # Pre-compute edge map once (expensive operation)
    y = clamp01(rgb_to_lum(result))
    gy, gx = np.gradient(y)
    grad = np.sqrt(gy*gy + gx*gx)
    edge_weight = np.exp(-grad * 10.0)[..., None]
    
    for _ in range(num_passes):
        # Use scipy's optimized Gaussian filter (much faster than manual convolution)
        blur = np.empty_like(result)
        for c in range(3):
            blur[..., c] = gaussian_filter(result[..., c], sigma=1.0, mode='nearest')
        
        # Color similarity (bilateral component)
        color_diff = np.sum(np.abs(result - blur), axis=2, keepdims=True)
        color_weight = np.exp(-color_diff * 5.0)
        
        # Combined weight (reuse pre-computed edge_weight)
        weight = edge_weight * color_weight
        
        # Blend based on weights
        result = result * (1 - weight) + blur * weight
    
    # Final blend with original based on amount
    return clamp01(rgb * (1.0 - amount) + result * amount)


def apply_defringe(rgb, amount=0.0):
    """
    Remove purple fringing (chromatic aberration).
    Target pixels where Red and Blue are high, but Green is low (Purple/Magenta).
    """
    if amount <= 1e-6:
        return rgb
    
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    
    # Detect purple: (R+B)/2 > G
    # We want a smooth mask.
    # Purple score = min(R, B) - G. If R,B are high and G is low, score is high.
    
    # Vectorized approach
    min_rb = np.minimum(r, b)
    purple_mask = np.maximum(0, min_rb - g)
    
    # Amplify the mask
    purple_mask = clamp01(purple_mask * 3.0)
    
    # Desaturate the purple areas towards Green (or Gray)
    lum = rgb_to_lum(rgb)
    
    # Blend original with desaturated version based on mask * amount
    mask = purple_mask * amount
    mask = mask[..., None]
    
    # Target color: Luminance (Gray)
    gray_rgb = np.stack([lum, lum, lum], axis=-1)
    
    return rgb * (1.0 - mask) + gray_rgb * mask


def apply_tone_curve(rgb, curve_amount=0.0):
    """
    Apply S-curve tone adjustment
    curve_amount: -1.0 to 1.0
    Positive = stronger S-curve (more contrast in midtones)
    Negative = inverted S-curve (less contrast)
    """
    if abs(curve_amount) < 1e-6:
        return rgb
    
    # Create S-curve using a simple polynomial
    # This creates a smooth curve that boosts highlights and shadows
    def s_curve(x, strength):
        # Cubic S-curve: y = 3x^2 - 2x^3 (base)
        # Adjusted with strength parameter
        if strength > 0:
            # Positive: enhance contrast
            return x + strength * (3 * x**2 - 2 * x**3 - x)
        else:
            # Negative: reduce contrast
            return x + strength * (x - 3 * x**2 + 2 * x**3)
    
    out = rgb.copy()
    for i in range(3):
        out[..., i] = s_curve(out[..., i], curve_amount)
    
    return np.clip(out, 0, 1)

def apply_curve_lut(rgb, lut):
    """
    Apply curve using lookup table
    lut: list/array of 256 elements with values 0-255
    """
    if lut is None:
        return rgb
    
    # Convert list to numpy array if needed
    if isinstance(lut, list):
        lut = np.array(lut, dtype=np.uint8)
    
    # Convert to 0-255 range
    rgb_int = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    
    # Apply LUT to each channel
    out = np.zeros_like(rgb)
    for i in range(3):
        out[..., i] = lut[rgb_int[..., i]]
    
    # Convert back to 0-1
    return out.astype(np.float32) / 255.0



def apply_vignette(rgb, amount=0.0):
    if abs(amount)<1e-6: return rgb
    h,w,_=rgb.shape
    y,x=np.ogrid[:h,:w]
    cy, cx = (h-1)/2.0, (w-1)/2.0
    ry = np.maximum(cy, 1.0); rx = np.maximum(cx, 1.0)
    dy = (y-cy)/ry; dx=(x-cx)/rx
    r2 = dx*dx + dy*dy
    mask = np.clip(1.0 - amount*r2, 0.2, 1.0)
    return clamp01(rgb*mask[...,None])

def apply_film_grain(rgb, amount=0.0, size=0.5, roughness=0.5):
    """
    Add film grain effect similar to Lightroom
    amount: grain intensity (0-1)
    size: grain size (0=fine, 1=coarse)
    roughness: grain texture (0=smooth, 1=rough)
    """
    if amount <= 1e-6:
        return rgb
    
    h, w, _ = rgb.shape
    
    # Generate noise pattern
    # Size controls the frequency of noise
    noise_scale = max(1, int(1 + size * 4))  # 1-5 pixels
    
    # Generate base noise at lower resolution
    noise_h = max(1, h // noise_scale)
    noise_w = max(1, w // noise_scale)
    noise = np.random.normal(0, 1, (noise_h, noise_w))
    
    # Resize to image size using scipy (much faster than PIL)
    from scipy.ndimage import zoom
    zoom_h = h / noise_h
    zoom_w = w / noise_w
    noise = zoom(noise, (zoom_h, zoom_w), order=1)  # order=1 is bilinear
    
    # Roughness controls the distribution
    if roughness > 0.5:
        # More rough = more extreme values
        power = 1.0 - (roughness - 0.5) * 0.8
        noise = np.sign(noise) * np.power(np.abs(noise), power)
    else:
        # More smooth = more gaussian
        noise = noise * (0.5 + roughness)
    
    # Apply grain with luminance-based modulation
    # Grain is more visible in midtones
    lum = rgb_to_lum(rgb)
    grain_mask = 1.0 - np.abs(lum - 0.5) * 2.0  # Peak at 0.5 luminance
    grain_mask = np.clip(grain_mask, 0.3, 1.0)  # Don't completely remove from highlights/shadows
    grain_mask = grain_mask[..., None]
    
    # Add grain
    grain_strength = amount * 0.12 * grain_mask
    out = rgb + noise[..., None] * grain_strength
    
    return np.clip(out, 0, 1)


def apply_unsharp(rgb, amount=0.0):
    if amount<=1e-6: return rgb
    pad=np.pad(rgb,((1,1),(1,1),(0,0)),mode='edge')
    blur=(pad[:-2,:-2]+pad[:-2,1:-1]+pad[:-2,2:]+pad[1:-1,:-2]+pad[1:-1,1:-1]+pad[1:-1,2:]+pad[2:,:-2]+pad[2:,1:-1]+pad[2:,2:])/9.0
    mask = rgb - blur
    return clamp01(rgb + mask*(1.5*amount))

def apply_mid_contrast(rgb, amount=0.0):
    """S-curve ดึง midtones"""
    if abs(amount)<1e-6: return rgb
    t = 0.5 + (rgb-0.5)*(1.0+1.6*amount)
    return clamp01(t)

def apply_clarity(rgb, amount=0.0):
    if abs(amount)<1e-6: return rgb
    pad=np.pad(rgb,((1,1),(1,1),(0,0)),mode='edge')
    blur=(pad[:-2,:-2]+pad[:-2,1:-1]+pad[:-2,2:]+pad[1:-1,:-2]+pad[1:-1,1:-1]+pad[1:-1,2:]+pad[2:,:-2]+pad[2:,1:-1]+pad[2:,2:])/9.0
    return clamp01(rgb+(rgb-blur)*(0.45*amount))

def apply_texture(rgb, amount=0.0):
    """เพิ่มคอนทราสต์รายละเอียดขนาดเล็ก (high-pass)"""
    if abs(amount)<1e-6: return rgb
    pad=np.pad(rgb,((1,1),(1,1),(0,0)),mode='edge')
    blur=(pad[:-2,:-2]+pad[:-2,1:-1]+pad[:-2,2:]+pad[1:-1,:-2]+pad[1:-1,1:-1]+pad[1:-1,2:]+pad[2:,:-2]+pad[2:,1:-1]+pad[2:,2:])/9.0
    high=rgb-blur
    return clamp01(rgb + high*(0.8*amount))

def rgb_to_hsv(rgb):
    r,g,b=rgb[...,0],rgb[...,1],rgb[...,2]
    mx=np.max(rgb,axis=2); mn=np.min(rgb,axis=2); diff=mx-mn
    h=np.zeros_like(mx); s=np.zeros_like(mx); v=mx
    mask=diff>1e-6
    r_eq=(mx==r)&mask; g_eq=(mx==g)&mask; b_eq=(mx==b)&mask
    h[r_eq]=(60*((g[r_eq]-b[r_eq])/diff[r_eq])+360)%360
    h[g_eq]=(60*((b[g_eq]-r[g_eq])/diff[g_eq])+120)%360
    h[b_eq]=(60*((r[b_eq]-g[b_eq])/diff[b_eq])+240)%360
    nz=mx>1e-6; s[nz]=diff[nz]/mx[nz]
    return h,s,v

def hsv_to_rgb(h,s,v):
    h=(h%360)/60.0; c=v*s; x=c*(1-abs(h%2-1)); m=v-c
    z=np.zeros_like(h); r=np.zeros_like(h); g=np.zeros_like(h); b=np.zeros_like(h)
    sets=[((0<=h)&(h<1),(c,x,z)),((1<=h)&(h<2),(x,c,z)),((2<=h)&(h<3),(z,c,x)),
          ((3<=h)&(h<4),(z,x,c)),((4<=h)&(h<5),(x,z,c)),((5<=h)&(h<6),(c,z,x))]
    for mask,(rr,gg,bb) in sets:
        r[mask]=rr[mask]; g[mask]=gg[mask]; b[mask]=bb[mask]
    return np.stack([r+m,g+m,b+m],axis=-1)

def _circ_dist(a,b): 
    d=np.abs(a-b)%360.0; return np.minimum(d,360.0-d)

def _color_weight(h, center, width=_COLOR_WIDTH):
    d=_circ_dist(h,center); w=np.clip(1.0-(d/width),0,1); return w*w*(3-2*w)

def apply_hsl_mixer(rgb, adj):
    # Check if any HSL adjustments are actually active before converting to HSV
    has_adj = False
    _COLOR_CENTERS = {"red":0.0,"orange":30.0,"yellow":60.0,"green":120.0,"aqua":180.0,"blue":240.0,"purple":280.0,"magenta":320.0}
    for name in _COLOR_CENTERS.keys():
        if abs(float(adj.get(f"h_{name}",0.0)))>1e-6 or abs(float(adj.get(f"s_{name}",0.0)))>1e-6 or abs(float(adj.get(f"l_{name}",0.0)))>1e-6:
            has_adj = True
            break
    if not has_adj:
        return rgb

    h,s,v=rgb_to_hsv(rgb); hn, sn, vn = h.copy(), s.copy(), v.copy()
    for name,center in _COLOR_CENTERS.items():
        w=_color_weight(h,center)
        dh=float(adj.get(f"h_{name}",0.0)); ds=float(adj.get(f"s_{name}",0.0)); dl=float(adj.get(f"l_{name}",0.0))
        if abs(dh)>1e-6: hn=(hn+dh*w)%360.0
        if abs(ds)>1e-6: sn=np.clip(sn*(1.0+ds*w),0,1)
        if abs(dl)>1e-6: vn=np.clip(vn+dl*w*0.5,0,1)
    return hsv_to_rgb(hn,sn,vn)

def pipeline(rgb01, adj, fast_mode=False):
    # Apply exposure first
    # [CHANGED] Do NOT clamp yet. Allow values > 1.0 for HDR highlights.
    x = rgb01 * (2.0**adj["exposure"])
    
    # Pixel-wise operations
    x = apply_white_balance(x, adj["temperature"], adj["tint"])
    
    # Tone mapping (Highlights/Shadows) handles the HDR compression
    x = apply_tone_regions(x, adj["highlights"], adj["shadows"], adj["whites"], adj["blacks"])
    
    # NOW we can safely clamp mid-pipeline if needed, but keeping float is better
    
    x = apply_dehaze(x, adj["dehaze"])
    
    # Denoise if not in fast mode
    if not fast_mode:
        x = apply_denoise(x, adj["denoise"])
    else:
        # Clamp once if skipping denoise to ensure safe range for next steps
        x = clamp01(x)
    
    # Color adjustments (safe range)
    x = apply_saturation_vibrance(x, adj["saturation"], adj["vibrance"])
    x = apply_contrast_gamma(x, adj["contrast"], adj["gamma"])
    x = apply_curve_lut(x, adj.get("curve_lut"))
    x = apply_mid_contrast(x, adj["mid_contrast"])
    
    # Convolution-based effects
    x = clamp01(apply_clarity(x, adj["clarity"]))
    x = apply_texture(x, adj["texture"])
    
    # HSL mixer
    x = apply_hsl_mixer(x, adj)
    
    # Final effects
    x = apply_vignette(x, adj["vignette"])
    
    # In fast mode, skip heavy final effects
    if not fast_mode:
        x = apply_defringe(x, adj.get("defringe", 0.0))
        x = apply_film_grain(x, adj.get("grain_amount", 0.0), adj.get("grain_size", 0.5), adj.get("grain_roughness", 0.5))
    
    # Final clamp to ensure [0,1] range
    return clamp01(x)

def process_image_fast(base_u8, adj, fast_mode=False):
    """
    Wrapper to use Rust extension if available.
    Uses hybrid approach: Rust for pixel-wise ops, Python for convolutions.
    base_u8: uint8 OR uint16 numpy array (H, W, 3)
    adj: dict of settings
    """
    is_16bit = (base_u8.dtype == np.uint16)
    
    if ninlab_core and not is_16bit:
        # Hybrid approach: Rust for pixel-wise, Python for convolutions
        try:
            # Rust expects HashMap<String, f32>. Filter out non-float values (like curve_lut which is list/None).
            rust_settings = {k: float(v) for k, v in adj.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
            
            # OPTIMIZATION: In fast mode, disable heavy effects (Denoise, Grain, Defringe)
            if fast_mode:
                rust_settings["denoise"] = 0.0
                rust_settings["grain_amount"] = 0.0
                rust_settings["defringe"] = 0.0
                # Clarity/Texture handled separate below (Python side), but good to zero them in Rust if eventually moved there
                rust_settings["clarity"] = 0.0
                rust_settings["texture"] = 0.0
            
            # Handle curve_lut separately
            lut = adj.get("curve_lut")
            lut_list = None
            if lut is not None:
                if isinstance(lut, list):
                    lut_list = lut
                elif isinstance(lut, np.ndarray):
                    lut_list = lut.astype(np.uint8).tolist()
            
            # Process with Rust (pixel-wise operations)
            result = ninlab_core.process_image(base_u8, rust_settings, lut_list)
            
            # Apply convolution-based effects in Python (not implemented in Rust yet)
            # Denoise and Film Grain are now in Rust!
            # Only Clarity and Texture remain in Python
            needs_convolution = (
                abs(adj.get("clarity", 0.0)) > 1e-6 or
                abs(adj.get("texture", 0.0)) > 1e-6
            )
            
            # In fast mode, skip convolution entirely
            if needs_convolution and not fast_mode:
                # Convert to float for convolution operations
                result_f = result.astype(np.float32) / 255.0
                
                # Apply convolution effects
                if abs(adj.get("clarity", 0.0)) > 1e-6:
                    result_f = apply_clarity(result_f, adj["clarity"])
                
                if abs(adj.get("texture", 0.0)) > 1e-6:
                    result_f = apply_texture(result_f, adj["texture"])
                
                # Convert back to uint8
                result = (np.clip(result_f, 0, 1) * 255.0 + 0.5).astype(np.uint8)
            
            return result
        except Exception as e:
            print(f"Rust execution failed: {e}")
            # Fallback to pure Python
            pass
            
    # Fallback/16-bit Pipeline
    if is_16bit:
        # High precision pipeline
        src01 = base_u8.astype(np.float32) / 65535.0
    else:
        src01 = base_u8.astype(np.float32) / 255.0
        
    out01 = pipeline(src01, adj, fast_mode=fast_mode)
    return (np.clip(out01,0,1)*255.0 + 0.5).astype(np.uint8)

def apply_transforms(arr_u8, adj):
    """ใช้ทรานส์ฟอร์ม (หมุน/กลับ/ครอป) หลังแต่งภาพเสร็จ"""
    out = arr_u8
    
    # 1. Apply fine angle adjustment first (for straightening tilted images)
    angle = float(adj.get("angle", 0.0))
    if abs(angle) > 1e-6:
        # Positive angle = counterclockwise rotation
        # Use expand=True to show the full rotated image without cropping
        out = np.array(Image.fromarray(out).rotate(-angle, resample=Image.BICUBIC, expand=True))
    
    # 2. Then apply 90° rotation (รองรับ 0/90/180/270 ได้ทันที, องศาอื่นจะใช้ PIL)
    rot = int(adj.get("rotate", 0)) % 360
    if rot in (90, 180, 270):
        k = rot // 90
        out = np.rot90(out, k).copy()
    elif rot != 0:
        out = np.array(Image.fromarray(out).rotate(-rot, resample=Image.BICUBIC, expand=True))

    # flip horizontal
    if bool(adj.get("flip_h", False)):
        out = np.ascontiguousarray(out[:, ::-1, :])

    # crop (normalized)
    c = adj.get("crop", None)
    if isinstance(c, dict):
        h, w, _ = out.shape
        x = max(0, min(1, float(c.get("x", 0))))
        y = max(0, min(1, float(c.get("y", 0))))
        cw = max(0, min(1, float(c.get("w", 1))))
        ch = max(0, min(1, float(c.get("h", 1))))
        x0 = int(round(x * w)); y0 = int(round(y * h))
        x1 = int(round((x+cw) * w)); y1 = int(round((y+ch) * h))
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 > x0 and y1 > y0:
            out = out[y0:y1, x0:x1, :].copy()
    # export sharpen (unsharp mask) — ทำหลัง transform
    sh = float(adj.get("export_sharpen", 0.0))
    if sh > 1e-6:
        out_f = out.astype(np.float32)/255.0
        out = (apply_unsharp(out_f, sh)*255.0+0.5).astype(np.uint8)
    return out

def preview_sharpen(arr_u8, amount):
    if amount <= 1e-6: return arr_u8
    arr = arr_u8.astype(np.float32)/255.0
    pad=np.pad(arr,((1,1),(1,1),(0,0)),mode='edge')
    blur=(pad[:-2,:-2]+pad[:-2,1:-1]+pad[:-2,2:]+pad[1:-1,:-2]+pad[1:-1,1:-1]+pad[1:-1,2:]+pad[2:,:-2]+pad[2:,1:-1]+pad[2:,2:])/9.0
    out = clamp01(arr + (arr - blur) * (0.8*amount))
    return (out*255.0+0.5).astype(np.uint8)

def decode_image(path, thumb_size=(72,48)):
    print(f"📂 decode_image called for: {path}")
    
    # Try loading from cache first
    try:
        from cache_manager import load_from_cache, save_to_cache
        cached = load_from_cache(path)
        if cached is not None:
            # Cache hit!
            print(f"  ✅ Loaded from cache")
            return cached['full'], cached['thumb']
        else:
            print(f"  ⚠️  Cache miss - will decode")
    except Exception as e:
        # Cache system failed, continue with normal decoding
        print(f"  ⚠️  Cache error: {e}")
        pass
    
    # MASTER TRY-EXCEPT: Catch all errors and return error image
    try:
        # Cache miss - proceed with decoding
        ext=os.path.splitext(path)[1].lower()
        print(f"  📄 File extension: {ext}")
        if ext in (".jpg",".jpeg",".png",".tif",".tiff"):
            try:
                img=Image.open(path)
                
                # Auto-rotate based on EXIF orientation
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
                
                img = img.convert("RGB")
                full=np.array(img,dtype=np.uint8)
            except Exception as e:
                print(f"Failed to open {ext} file: {e}")
                err_img = create_error_image(thumb_size, f"Failed to open {ext.upper()}:\n{str(e)}")
                return err_img, err_img
        elif rawpy is not None:
            # Special handling for Canon CR3 to avoid LibRaw errors and improve performance
            if ext == ".cr3":
                print(f"Attempting fast preview extraction for {path}...")
                full = None
                best_img = None  # Initialize to prevent NameError
                
                # Strategy 1: Smart Binary Scan (PRVW atom / JPEG)
                try:
                    import mmap
                    import struct
                    from io import BytesIO
                    
                    with open(path, 'rb') as f:
                        # Use mmap for zero-copy searching (much faster than reading 25MB)
                        # 0 means map the whole file
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            
                            # Search for PRVW atom (Canon Preview)
                            prvw_idx = mm.find(b'PRVW')
                            
                            if prvw_idx != -1:
                                # 1. Parsing PRVW Box Size (Standard 32-bit Box)
                                # Size is the 4 bytes BEFORE 'PRVW'
                                if prvw_idx >= 4:
                                    size_val = struct.unpack('>I', mm[prvw_idx-4:prvw_idx])[0]
                                    
                                    # Safety check on size
                                    if 200 < size_val < 50_000_000:
                                        # Extract ONLY the preview box data
                                        start_box = prvw_idx - 4
                                        end_box = start_box + size_val
                                        
                                        # Ensure we don't go out of bounds
                                        if end_box <= mm.size():
                                            box_data = mm[start_box:end_box]
                                            
                                            # Now search for JPEG inside this small buffer
                                            jpg_start = box_data.find(b'\xff\xd8')
                                            if jpg_start != -1:
                                                stream = BytesIO(box_data[jpg_start:])
                                                img = Image.open(stream)
                                                if img.width > 320:
                                                     best_img = img
            
            
                            # Fallback: If no PRVW or parsing failed, do a Deep Scan
                            if best_img is None:
                                limit = min(mm.size(), 100 * 1024 * 1024)
                                search_area = mm[:limit] 
                                start = 0
                                
                                for _ in range(50):
                                    idx = search_area.find(b'\xff\xd8', start)
                                    if idx == -1: break
                                    
                                    try:
                                        stream = BytesIO(search_area[idx:])
                                        img = Image.open(stream)
                                        
                                        if img.width > 160:
                                             pixels = img.width * img.height
                                             
                                             if best_img is None:
                                                 best_img = img
                                             else:
                                                 current_pixels = best_img.width * best_img.height
                                                 if pixels > current_pixels:
                                                     best_img = img
                                             
                                             if best_img.width * best_img.height > 2000000:
                                                 break
                                    except:
                                        pass
                                        
                                    start = idx + 2
                        
                        if best_img:
                            # Robust Orientation Handling
                            # 1. Check if the image already has orientation info (Standard PIL)
                            has_pil_orientation = False
                            try:
                                exif = best_img.getexif()
                                if exif and 274 in exif: # 274 = Orientation
                                    if exif[274] != 1: # Only trust if it requires rotation
                                        has_pil_orientation = True
                            except:
                                pass
                            
                            # 2. If PIL sees orientation, let PIL handle it
                            if has_pil_orientation:
                                from PIL import ImageOps
                                best_img = ImageOps.exif_transpose(best_img)
                                
                            # 3. If PIL didn't see orientation (common in CR3 preview streams), find it externally
                            else:
                                orientation = None
                                
                                # Try ExifRead on stream (if we could, but stream is gone/hard to reconstruct perfectly)
                                # Let's go straight to ExifTool for robust fallback which matches the file container
                                import subprocess
                                import json
                                
                                exiftool_path = None
                                possible_locations = [
                                    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exiftool.exe'),
                                    os.path.join(os.getcwd(), 'exiftool.exe'),
                                    'exiftool.exe',
                                ]
                                for loc in possible_locations:
                                    if os.path.isfile(loc):
                                        exiftool_path = loc
                                        break
                                
                                if exiftool_path:
                                    try:
                                        # Use -n to get numeric value
                                        result = subprocess.run(
                                            [exiftool_path, '-Orientation', '-n', '-j', str(path)],
                                            capture_output=True,
                                            text=True,
                                            timeout=1
                                        )
                                        if result.returncode == 0 and result.stdout:
                                            data = json.loads(result.stdout)[0]
                                            orientation = data.get('Orientation')
                                    except:
                                        pass
                                
                                # 4. Apply Manual Rotation based on external orientation
                                if orientation:
                                    try:
                                        val = int(orientation)
                                        if val == 3: # Rotate 180
                                            best_img = best_img.rotate(180, expand=True)
                                            # print(f"  🔄 External Force Rotated 180°")
                                        elif val == 6: # Rotate 90 CW
                                            best_img = best_img.rotate(270, expand=True) # 270 CCW
                                            # print(f"  🔄 External Force Rotated 90° CW")
                                        elif val == 8: # Rotate 270 CW
                                            best_img = best_img.rotate(90, expand=True) # 90 CCW
                                            # print(f"  🔄 External Force Rotated 270° CW")
                                    except:
                                        pass
                            
                            if best_img.mode != "RGB":
                                best_img = best_img.convert("RGB")
                                
                            MAX_PREVIEW_SIZE = 6000
                            if best_img.width > MAX_PREVIEW_SIZE or best_img.height > MAX_PREVIEW_SIZE:
                                best_img.thumbnail((MAX_PREVIEW_SIZE, MAX_PREVIEW_SIZE), Image.LANCZOS)
                                
                            full = np.array(best_img, dtype=np.uint8)
                            
                except Exception as e_scan:
                    print(f"Binary scan failed: {e_scan}")

                # Strategy 2: ExifTool (If available)
                if full is None:
                    try:
                        import subprocess
                        for tag in ['-PreviewImage', '-JpgFromRaw', '-ThumbnailImage']:
                            try:
                                res = subprocess.run(['exiftool', '-b', tag, str(path)], 
                                                  capture_output=True, check=True)
                                if res.stdout and res.stdout.startswith(b'\xff\xd8'):
                                    from io import BytesIO
                                    from PIL import ImageOps
                                    img = Image.open(BytesIO(res.stdout))
                                    # Robust Orientation Handling
                                    # 1. Check if the image already has orientation info (Standard PIL)
                                    has_pil_orientation = False
                                    try:
                                        exif = img.getexif()
                                        if exif and 274 in exif: # 274 = Orientation
                                            if exif[274] != 1: # Only trust if it requires rotation
                                                has_pil_orientation = True
                                    except:
                                        pass
                                    
                                    # 2. If PIL sees orientation, let PIL handle it
                                    from PIL import ImageOps
                                    if has_pil_orientation:
                                        img = ImageOps.exif_transpose(img)
                                        
                                    # 3. If PIL didn't see orientation, find it externally
                                    else:
                                        orientation = None
                                        
                                        # Try ExifTool on the main file
                                        try:
                                            if exiftool_path: # Re-use path
                                                # Use -n to get numeric value
                                                result = subprocess.run(
                                                    [exiftool_path, '-Orientation', '-n', '-j', str(path)],
                                                    capture_output=True,
                                                    text=True,
                                                    timeout=1
                                                )
                                                if result.returncode == 0 and result.stdout:
                                                    data = json.loads(result.stdout)[0]
                                                    orientation = data.get('Orientation')
                                        except:
                                            pass
                                        
                                        # 4. Apply Manual Rotation based on external orientation
                                        if orientation:
                                            try:
                                                val = int(orientation)
                                                if val == 3: # Rotate 180
                                                    img = img.rotate(180, expand=True)
                                                elif val == 6: # Rotate 90 CW
                                                    img = img.rotate(270, expand=True) # 270 CCW
                                                elif val == 8: # Rotate 270 CW
                                                    img = img.rotate(90, expand=True) # 90 CCW
                                            except:
                                                pass
                                    
                                    img = img.convert("RGB")
                                    MAX_PREVIEW_SIZE = 6000
                                    if img.width > MAX_PREVIEW_SIZE or img.height > MAX_PREVIEW_SIZE:
                                        img.thumbnail((MAX_PREVIEW_SIZE, MAX_PREVIEW_SIZE), Image.LANCZOS)
                                    full = np.array(img, dtype=np.uint8)
                                    break
                            except:
                                continue
                    except:
                        pass

                # If preview extraction failed, try rawpy as last resort
                if full is None:
                    try:
                        with rawpy.imread(path) as raw:
                             full=raw.postprocess(
                                use_camera_wb=True,
                                no_auto_bright=False,
                                bright=1.0,
                                user_sat=None,
                                output_bps=16
                            )
                        
                        # Auto-rotate based on EXIF orientation
                        # Read orientation from file using ExifTool
                        try:
                            import subprocess
                            import json
                            
                            # Find exiftool
                            exiftool_path = None
                            possible_locations = [
                                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exiftool.exe'),
                                os.path.join(os.getcwd(), 'exiftool.exe'),
                                'exiftool.exe',
                            ]
                            for loc in possible_locations:
                                if os.path.isfile(loc):
                                    exiftool_path = loc
                                    break
                            
                            if exiftool_path:
                                result = subprocess.run(
                                    [exiftool_path, '-Orientation', '-j', str(path)],
                                    capture_output=True,
                                    text=True,
                                    timeout=2
                                )
                                
                                if result.returncode == 0 and result.stdout:
                                    data = json.loads(result.stdout)[0]
                                    orientation = data.get('Orientation', '')
                                    
                                    # Rotate based on orientation
                                    if 'Rotate 90 CW' in orientation or orientation == 6:
                                        full = np.rot90(full, k=-1)
                                        print(f"  🔄 Rotated 90° CW")
                                    elif 'Rotate 270 CW' in orientation or orientation == 8:
                                        full = np.rot90(full, k=1)
                                        print(f"  🔄 Rotated 270° CW (90° CCW)")
                                    elif 'Rotate 180' in orientation or orientation == 3:
                                        full = np.rot90(full, k=2)
                                        print(f"  🔄 Rotated 180°")
                        except Exception as e:
                            print(f"  ⚠️  Could not apply rotation: {e}")
                            
                    except Exception as e:
                        print(f"CR3 decode failed: {e}")
                        err_img = create_error_image(thumb_size, f"CR3 Error:\n{str(e)}")
                        return err_img, err_img

            else:
                # Normal handling for other RAWs (ARW, NEF, etc)
                try:
                    with rawpy.imread(path) as raw:
                        full=raw.postprocess(
                            use_camera_wb=True,
                            no_auto_bright=False,
                            bright=1.0,
                            user_sat=None,
                            output_bps=16
                        )
                    
                    # Auto-rotate based on EXIF orientation
                    # Read orientation from file using ExifTool
                    try:
                        import subprocess
                        import json
                        
                        # Find exiftool
                        exiftool_path = None
                        possible_locations = [
                            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exiftool.exe'),
                            os.path.join(os.getcwd(), 'exiftool.exe'),
                            'exiftool.exe',
                        ]
                        for loc in possible_locations:
                            if os.path.isfile(loc):
                                exiftool_path = loc
                                break
                        
                        if exiftool_path:
                            result = subprocess.run(
                                [exiftool_path, '-Orientation', '-j', str(path)],
                                capture_output=True,
                                text=True,
                                timeout=2
                            )
                            
                            if result.returncode == 0 and result.stdout:
                                data = json.loads(result.stdout)[0]
                                orientation = data.get('Orientation', '')
                                
                                # Rotate based on orientation
                                if 'Rotate 90 CW' in orientation or orientation == 6:
                                    full = np.rot90(full, k=-1)
                                    print(f"  🔄 Rotated 90° CW")
                                elif 'Rotate 270 CW' in orientation or orientation == 8:
                                    full = np.rot90(full, k=1)
                                    print(f"  🔄 Rotated 270° CW (90° CCW)")
                                elif 'Rotate 180' in orientation or orientation == 3:
                                    full = np.rot90(full, k=2)
                                    print(f"  🔄 Rotated 180°")
                    except Exception as e:
                        print(f"  ⚠️  Could not apply rotation: {e}")
                        
                except Exception as e:
                    print(f"RAW decode failed: {e}")
                    err_img = create_error_image(thumb_size, f"RAW Error:\n{str(e)}")
                    return err_img, err_img
        else:
            err_img = create_error_image(thumb_size, "RAW support requires 'rawpy'")
            return err_img, err_img

        # Generate 8-bit thumbnail
        try:
            # Safety check
            if full is None:
                err_img = create_error_image(thumb_size, "Decoding failed: No image data")
                return err_img, err_img
            
            if full.dtype == np.uint16:
                # Simple compression for thumbnail
                thumb_arr = (full >> 8).astype(np.uint8)
            else:
                thumb_arr = full
                
            thumb=Image.fromarray(thumb_arr).copy()
            thumb.thumbnail(thumb_size, Image.BILINEAR)
            thumb=np.array(thumb,dtype=np.uint8)
        except Exception as e:
            print(f"Thumbnail generation failed: {e}")
            err_img = create_error_image(thumb_size, f"Thumbnail error:\n{str(e)}")
            return err_img, err_img
        
        # Save to cache for next time
        try:
            from cache_manager import save_to_cache
            save_to_cache(path, full, thumb)
        except Exception:
            # Cache save failed, but decoding succeeded - continue
            pass
        
        return full, thumb
    
    except Exception as e:
        # Master exception handler
        import traceback
        print(f"❌ Unexpected decode error for {path}")
        print(f"   Error: {str(e)}")
        print(f"   Traceback:\n{traceback.format_exc()}")
        err_img = create_error_image(thumb_size, f"Error:\n{str(e)}")
        return err_img, err_img

def get_image_metadata(path):
    """
    Extract metadata from image file.
    Returns a dict with keys: Name, Size, Dimensions, Camera, ISO, Aperture, Shutter, Lens, Date
    """
    import os  # Import here to avoid scope issues
    
    meta = {
        "Name": os.path.basename(path),
        "Size": f"{os.path.getsize(path) / (1024*1024):.2f} MB",
        "Dimensions": "-",
        "Camera": "-",
        "ISO": "-",
        "Aperture": "-",
        "Shutter": "-",
        "Lens": "-",
        "Date": "-"
    }
    
    try:
        ext = os.path.splitext(path)[1].lower()
        
        # Use exiftool for RAW files (best support for all RAW formats including CR3)
        if ext in ('.arw', '.cr2', '.cr3', '.nef', '.dng', '.orf', '.raf', '.rw2'):
            try:
                import subprocess
                import json
                
                # Try to use exiftool (if installed)
                result = subprocess.run(
                    ['exiftool', '-j', '-Model', '-ISO', '-FNumber', '-ExposureTime', 
                     '-LensModel', '-DateTimeOriginal', '-ImageWidth', '-ImageHeight', path],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0 and result.stdout:
                    data = json.loads(result.stdout)[0]
                    
                    if 'Model' in data:
                        meta["Camera"] = str(data['Model']).strip()
                    
                    if 'ISO' in data:
                        meta["ISO"] = str(data['ISO'])
                    
                    if 'FNumber' in data or 'Aperture' in data:
                        fnum = data.get('FNumber', data.get('Aperture', ''))
                        if fnum:
                            try:
                                meta["Aperture"] = f"f/{float(fnum):.1f}"
                            except:
                                meta["Aperture"] = str(fnum)
                    
                    if 'ExposureTime' in data or 'ShutterSpeed' in data:
                        exp = data.get('ExposureTime', data.get('ShutterSpeed', ''))
                        if exp:
                            try:
                                if isinstance(exp, str) and '/' in exp:
                                    parts = exp.split('/')
                                    if int(parts[0]) == 1:
                                        meta["Shutter"] = f"1/{parts[1]}s"
                                    else:
                                        meta["Shutter"] = f"{int(parts[0])/int(parts[1]):.2f}s"
                                else:
                                    val = float(exp)
                                    if val < 1:
                                        meta["Shutter"] = f"1/{int(1/val)}s"
                                    else:
                                        meta["Shutter"] = f"{val:.2f}s"
                            except:
                                meta["Shutter"] = str(exp)
                    
                    if 'LensModel' in data:
                        meta["Lens"] = str(data['LensModel']).strip()
                    
                    if 'DateTimeOriginal' in data:
                        meta["Date"] = str(data['DateTimeOriginal'])
                    elif 'CreateDate' in data:
                        meta["Date"] = str(data['CreateDate'])
                    
                    if 'ImageWidth' in data and 'ImageHeight' in data:
                        meta["Dimensions"] = f"{data['ImageWidth']} x {data['ImageHeight']}"
                        
            except FileNotFoundError:
                # Exiftool not installed, fall back to exifread
                try:
                    import exifread
                    with open(path, 'rb') as f:
                        tags = exifread.process_file(f, details=False)
                        
                        if 'Image Model' in tags:
                            meta["Camera"] = str(tags['Image Model']).strip()
                        
                        if 'EXIF ISOSpeedRatings' in tags:
                            meta["ISO"] = str(tags['EXIF ISOSpeedRatings'])
                        
                        if 'EXIF FNumber' in tags:
                            try:
                                fnum = tags['EXIF FNumber']
                                if hasattr(fnum, 'values') and len(fnum.values) > 0:
                                    val = fnum.values[0]
                                    if hasattr(val, 'num') and hasattr(val, 'den'):
                                        meta["Aperture"] = f"f/{val.num/val.den:.1f}"
                                    else:
                                        meta["Aperture"] = f"f/{float(val):.1f}"
                                else:
                                    meta["Aperture"] = str(fnum)
                            except:
                                pass
                        
                        if 'EXIF ExposureTime' in tags:
                            try:
                                exp = tags['EXIF ExposureTime']
                                if hasattr(exp, 'values') and len(exp.values) > 0:
                                    val = exp.values[0]
                                    if hasattr(val, 'num') and hasattr(val, 'den'):
                                        if val.num == 1:
                                            meta["Shutter"] = f"1/{val.den}s"
                                        else:
                                            meta["Shutter"] = f"{val.num/val.den:.2f}s"
                                    else:
                                        v = float(val)
                                        if v < 1:
                                            meta["Shutter"] = f"1/{int(1/v)}s"
                                        else:
                                            meta["Shutter"] = f"{v:.2f}s"
                                else:
                                    meta["Shutter"] = str(exp)
                            except:
                                pass
                        
                        if 'EXIF LensModel' in tags:
                            meta["Lens"] = str(tags['EXIF LensModel']).strip()
                        
                        if 'EXIF DateTimeOriginal' in tags:
                            meta["Date"] = str(tags['EXIF DateTimeOriginal'])
                        elif 'Image DateTime' in tags:
                            meta["Date"] = str(tags['Image DateTime'])
                except:
                    pass
            except (subprocess.TimeoutExpired, Exception) as e:
                print(f"exiftool error: {e}, falling back to rawpy")
    except:
        pass
            
    # For RAW files: Try ExifTool first (if available), then fallback to embedded EXIF
    RAW_EXTENSIONS = ('.cr3', '.arw', '.nef', '.dng', '.orf', '.raf', '.rw2', '.cr2', '.nrw')
    if ext in RAW_EXTENSIONS:
        # Try to find ExifTool
        exiftool_path = None
        import os
        possible_locations = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exiftool.exe'),  # Same dir as imaging.py
            os.path.join(os.getcwd(), 'exiftool.exe'),  # Current working directory
            'exiftool.exe',  # In PATH
            'exiftool',  # In PATH (no .exe)
        ]
        
        for loc in possible_locations:
            if os.path.isfile(loc):
                exiftool_path = loc
                break
        
        # Try ExifTool if found
        if exiftool_path:
            print(f"🔍 Using ExifTool for metadata: {ext.upper()}")
            try:
                import subprocess
                import json
                
                result = subprocess.run(
                    [exiftool_path, '-j', '-Model', '-ISO', '-ExposureTime', '-FNumber',
                     '-LensModel', '-DateTimeOriginal', '-ImageWidth', '-ImageHeight', str(path)],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0 and result.stdout:
                    data = json.loads(result.stdout)[0]
                    
                    if 'Model' in data:
                        meta["Camera"] = str(data['Model']).strip()
                        print(f"  ✓ Camera: {meta['Camera']}")
                    if 'ISO' in data:
                        meta["ISO"] = str(data['ISO'])
                        print(f"  ✓ ISO: {meta['ISO']}")
                    if 'ExposureTime' in data:
                        exp = data['ExposureTime']
                        meta["Shutter"] = f"{exp}s" if isinstance(exp, str) and '/' in exp else f"{exp}s"
                        print(f"  ✓ Shutter: {meta['Shutter']}")
                    if 'FNumber' in data:
                        meta["Aperture"] = f"f/{data['FNumber']}"
                        print(f"  ✓ Aperture: {meta['Aperture']}")
                    if 'LensModel' in data:
                        meta["Lens"] = str(data['LensModel']).strip()
                        print(f"  ✓ Lens: {meta['Lens']}")
                    if 'DateTimeOriginal' in data:
                        meta["Date"] = str(data['DateTimeOriginal'])
                        print(f"  ✓ Date: {meta['Date']}")
                    if 'ImageWidth' in data and 'ImageHeight' in data:
                        meta["Dimensions"] = f"{data['ImageWidth']} x {data['ImageHeight']}"
                        print(f"  ✓ Dimensions: {meta['Dimensions']}")
                else:
                    print(f"  ⚠️  ExifTool returned no data")
            except Exception as e:
                print(f"  ⚠️  ExifTool failed: {e}")
        
        # Fallback: Extract EXIF from embedded JPEG preview
        if meta["Camera"] == "-" or meta["ISO"] == "-":
            print(f"🔍 Attempting EXIF extraction from embedded preview for {ext.upper()}: {path}")
        try:
            import mmap
            import struct
            from io import BytesIO
            from PIL import Image as PILImage
            from PIL.ExifTags import TAGS
            
            # Find embedded JPEG preview in RAW file
            with open(path, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    # Search for JPEG markers
                    idx = mm.find(b'\xff\xd8')
                    
                    if idx != -1:
                        # Found JPEG, try to extract EXIF from it
                        try:
                            import exifread
                            
                            # Create a file-like object from the JPEG data
                            stream = BytesIO(mm[idx:idx+500000])  # Read first 500KB for EXIF
                            tags = exifread.process_file(stream, details=False)
                            
                            if tags:
                                print(f"  ✓ Found EXIF in embedded preview ({len(tags)} tags)")
                                print(f"  🔧 Available tags: {', '.join(list(tags.keys())[:20])}")  # Show first 20 tags
                                
                                # Camera Model
                                if meta["Camera"] == "-":
                                    if 'Image Model' in tags:
                                        meta["Camera"] = str(tags['Image Model']).strip()
                                        print(f"  ✓ Camera: {meta['Camera']}")
                                
                                # ISO
                                if meta["ISO"] == "-":
                                    if 'EXIF ISOSpeedRatings' in tags:
                                        meta["ISO"] = str(tags['EXIF ISOSpeedRatings'])
                                        print(f"  ✓ ISO: {meta['ISO']}")
                                
                                # Shutter Speed
                                if meta["Shutter"] == "-":
                                    if 'EXIF ExposureTime' in tags:
                                        exp = tags['EXIF ExposureTime']
                                        if hasattr(exp, 'values') and len(exp.values) > 0:
                                            val = exp.values[0]
                                            if hasattr(val, 'num') and hasattr(val, 'den'):
                                                if val.num == 1:
                                                    meta["Shutter"] = f"1/{val.den}s"
                                                else:
                                                    meta["Shutter"] = f"{val.num/val.den:.2f}s"
                                            else:
                                                v = float(val)
                                                if v < 1:
                                                    meta["Shutter"] = f"1/{int(1/v)}s"
                                                else:
                                                    meta["Shutter"] = f"{v:.2f}s"
                                        else:
                                            meta["Shutter"] = str(exp)
                                        print(f"  ✓ Shutter: {meta['Shutter']}")
                                
                                # Aperture
                                if meta["Aperture"] == "-":
                                    if 'EXIF FNumber' in tags:
                                        fnum = tags['EXIF FNumber']
                                        if hasattr(fnum, 'values') and len(fnum.values) > 0:
                                            val = fnum.values[0]
                                            if hasattr(val, 'num') and hasattr(val, 'den'):
                                                meta["Aperture"] = f"f/{val.num/val.den:.1f}"
                                            else:
                                                meta["Aperture"] = f"f/{float(val):.1f}"
                                        else:
                                            meta["Aperture"] = str(fnum)
                                        print(f"  ✓ Aperture: {meta['Aperture']}")
                                
                                # Lens Model
                                if meta["Lens"] == "-":
                                    if 'EXIF LensModel' in tags:
                                        meta["Lens"] = str(tags['EXIF LensModel']).strip()
                                        print(f"  ✓ Lens: {meta['Lens']}")
                                
                                # Date
                                if meta["Date"] == "-":
                                    if 'EXIF DateTimeOriginal' in tags:
                                        meta["Date"] = str(tags['EXIF DateTimeOriginal'])
                                        print(f"  ✓ Date: {meta['Date']}")
                                    elif 'Image DateTime' in tags:
                                        meta["Date"] = str(tags['Image DateTime'])
                                        print(f"  ✓ Date: {meta['Date']}")
                            else:
                                print(f"  ⚠️  No EXIF found in embedded preview")
                        except Exception as e:
                            print(f"  ⚠️  Could not extract EXIF from preview: {e}")
                    else:
                        print(f"  ⚠️  No JPEG preview found in file")
                        
        except Exception as e:
            print(f"  ⚠️  Preview EXIF extraction failed: {e}")
            import traceback
            traceback.print_exc()
            pass
    
    # For JPEG/PNG: Direct EXIF extraction
    elif ext in ('.jpg', '.jpeg', '.png', '.tif', '.tiff'):
        print(f"🔍 Attempting EXIF extraction for {ext.upper()}: {path}")
        try:
            from PIL import Image as PILImage
            from PIL.ExifTags import TAGS
            
            with PILImage.open(path) as img:
                exif = img.getexif()
                
                if exif:
                    # Camera Model
                    if meta["Camera"] == "-":
                        model = exif.get(272)
                        if model:
                            meta["Camera"] = str(model).strip()
                            print(f"  ✓ Camera: {meta['Camera']}")
                    
                    # ISO
                    if meta["ISO"] == "-":
                        iso = exif.get(34855)
                        if iso:
                            meta["ISO"] = str(iso)
                            print(f"  ✓ ISO: {meta['ISO']}")
                    
                    # Date
                    if meta["Date"] == "-":
                        date = exif.get(36867) or exif.get(306)
                        if date:
                            meta["Date"] = str(date)
                            print(f"  ✓ Date: {meta['Date']}")
        except Exception as e:
            print(f"  ⚠️  EXIF extraction failed: {e}")

    # Fallback: Try rawpy for Dimensions if still missing
    if rawpy is not None and ext in RAW_EXTENSIONS:
        if meta["Dimensions"] == "-":
            print(f"🔍 Attempting rawpy for dimensions: {ext.upper()}")
            try:
                with rawpy.imread(path) as raw:
                    if hasattr(raw, 'sizes'):
                         meta["Dimensions"] = f"{raw.sizes.width} x {raw.sizes.height}"
                         print(f"  ✓ Dimensions: {meta['Dimensions']}")
            except Exception as e:
                print(f"❌ Rawpy error for {path}: {e}")
                pass
            

    # CR3 Fallback: If Camera model is still missing (ExifTool failed/missing)
    if meta["Camera"] == "-" and ext == '.cr3':
        try:
            with open(path, 'rb') as f:
                # Read start of file
                header = f.read(8192) # First 8KB should contain the Make/Model
                
                # Search for "Canon EOS"
                try:
                    idx = header.find(b'Canon EOS')
                    if idx != -1:
                        # Extract string until null byte or non-printable
                        end = idx
                        while end < len(header) and 32 <= header[end] <= 126:
                            end += 1
                        
                        model_str = header[idx:end].decode('utf-8', errors='ignore')
                        if len(model_str) > 5:
                            meta["Camera"] = model_str.strip()
                except:
                    pass
        except:
            pass
        
    # For JPEG/PNG/TIFF, use PIL if dimensions/camera missing
    if ext not in ('.arw', '.cr2', '.cr3', '.nef', '.dng', '.orf', '.raf', '.rw2'):
        try:
            img = Image.open(path)
            if meta["Dimensions"] == "-":
                meta["Dimensions"] = f"{img.width} x {img.height}"
                
                # Extract EXIF
                exif = img._getexif()
                if exif:
                    from PIL.ExifTags import TAGS
                    for tag_id, value in exif.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag == "Model": 
                            meta["Camera"] = str(value).strip()
                        elif tag == "ISOSpeedRatings": 
                            meta["ISO"] = str(value)
                        elif tag == "FNumber": 
                            if isinstance(value, tuple):
                                meta["Aperture"] = f"f/{value[0]/value[1]:.1f}"
                            else:
                                meta["Aperture"] = f"f/{float(value):.1f}"
                        elif tag == "ExposureTime": 
                            if isinstance(value, tuple):
                                if value[0] == 1:
                                    meta["Shutter"] = f"1/{value[1]}s"
                                else:
                                    meta["Shutter"] = f"{value[0]/value[1]:.2f}s"
                            else:
                                meta["Shutter"] = f"{value}s"
                        elif tag == "LensModel": 
                            meta["Lens"] = str(value).strip()
                        elif tag == "DateTimeOriginal": 
                            meta["Date"] = str(value)
        except Exception as e:
            print(f"PIL error: {e}")
                

        
    return meta


def create_error_image(size, text):
    """Creates a placeholder image with error text"""
    try:
        from PIL import ImageDraw
        img = Image.new('RGB', (800, 600), color=(50, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((10, 50), text, fill=(255, 255, 255))
        img.thumbnail(size, Image.LANCZOS)
        return np.array(img, dtype=np.uint8)
    except:
        # If even error image creation fails, return black image
        return np.zeros((size[1], size[0], 3), dtype=np.uint8)

