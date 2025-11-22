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
    print("Rust extension not found, using Python fallback.")

def clamp01(a): 
    return np.clip(a, 0, 1, out=a)

# ค่าตั้งต้น (รวมทรานส์ฟอร์ม)
DEFAULTS = {
    "exposure":0.0,"contrast":0.0,"highlights":0.0,"shadows":0.0,"whites":0.0,"blacks":0.0,
    "saturation":0.0,"vibrance":0.0,"temperature":0.0,"tint":0.0,"gamma":1.0,
    "clarity":0.0,"texture":0.0,"mid_contrast":0.0,"dehaze":0.0,"denoise":0.0,
    "vignette":0.0,"export_sharpen":0.2,"tone_curve":0.0,"curve_lut":None,
    **{f"h_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    **{f"s_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    **{f"l_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    # transforms
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
    r=1+0.8*temperature-0.2*tint; g=1-0.1*temperature+0.4*tint; b=1-0.8*temperature-0.2*tint
    out=rgb.copy(); out[...,0]*=r; out[...,1]*=g; out[...,2]*=b; return out

def apply_tone_regions(rgb, hi=0.0, sh=0.0, wh=0.0, bl=0.0):
    y=clamp01(rgb_to_lum(rgb)); out=rgb.copy()
    if abs(sh)>1e-6:
        w=np.clip(1.0-(y*2.0),0,1); out=out*(1-w[...,None])+(out*(1+0.8*sh))*w[...,None]
    if abs(hi)>1e-6:
        w=np.clip((y*2.0-1.0),0,1); out=out*(1-w[...,None])+(out*(1-0.8*hi))*w[...,None]
    if abs(wh)>1e-6: out=np.minimum(out*(1.0+wh*0.6),1.0)
    if abs(bl)>1e-6: out=np.maximum(out+bl*0.4,0.0)
    return out

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
    """ลด noise แบบ edge-aware ง่าย ๆ"""
    if amount<=1e-6: return rgb
    pad=np.pad(rgb,((1,1),(1,1),(0,0)),mode='edge')
    blur=(pad[:-2,:-2]+pad[:-2,1:-1]+pad[:-2,2:]+pad[1:-1,:-2]+pad[1:-1,1:-1]+pad[1:-1,2:]+pad[2:,:-2]+pad[2:,1:-1]+pad[2:,2:])/9.0
    y = clamp01(rgb_to_lum(rgb))
    gy, gx = np.gradient(y)
    grad = np.abs(gy) + np.abs(gx)
    w=np.exp(-grad*6.0)  # ขึ้นกับความชันของความสว่าง
    mix = w[...,None]
    out = rgb*mix + blur*(1.0-mix)
    return clamp01(rgb*(1.0-amount) + out*amount)

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
    x=clamp01(rgb01*(2.0**adj["exposure"]))
    x=clamp01(apply_white_balance(x,adj["temperature"],adj["tint"]))
    x=clamp01(apply_tone_regions(x,adj["highlights"],adj["shadows"],adj["whites"],adj["blacks"]))
    x=clamp01(apply_dehaze(x, adj["dehaze"]))
    if not fast_mode:
        x=clamp01(apply_denoise(x, adj["denoise"]))
    x=clamp01(apply_saturation_vibrance(x,adj["saturation"],adj["vibrance"]))
    x=clamp01(apply_contrast_gamma(x,adj["contrast"],adj["gamma"]))
    x=clamp01(apply_curve_lut(x, adj.get("curve_lut")))
    x=clamp01(apply_mid_contrast(x, adj["mid_contrast"]))
    x=clamp01(apply_clarity(x,adj["clarity"]))
    x=clamp01(apply_texture(x, adj["texture"]))
    x=clamp01(apply_hsl_mixer(x,adj))
    x=clamp01(apply_vignette(x, adj["vignette"]))
    return x

def process_image_fast(base_u8, adj, fast_mode=False):
    """
    Wrapper to use Rust extension if available.
    base_u8: uint8 numpy array (H, W, 3)
    adj: dict of settings
    """
    if ninlab_core:
        # Rust implementation
        # Note: Rust pipeline currently implements pixel-wise ops.
        # Convolutions (Denoise, Clarity, Texture) are not yet in Rust.
        # But for 'fast_mode' (live preview), we usually skip Denoise anyway.
        # For full export, we might miss Clarity/Texture if we rely solely on Rust.
        # Ideally, we should implement them in Rust or do a hybrid approach.
        # For now, let's use Rust for the heavy lifting.
        try:
            # Rust expects HashMap<String, f32>. Filter out non-float values (like curve_lut which is list/None).
            rust_settings = {k: float(v) for k, v in adj.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
            
            # Handle curve_lut separately
            lut = adj.get("curve_lut")
            lut_list = None
            if lut is not None:
                if isinstance(lut, list):
                    lut_list = lut
                elif isinstance(lut, np.ndarray):
                    lut_list = lut.astype(np.uint8).tolist()
            
            return ninlab_core.process_image(base_u8, rust_settings, lut_list)
        except Exception as e:
            print(f"Rust execution failed: {e}")
            # Fallback
            pass
            
    # Fallback to NumPy
    src01 = base_u8.astype(np.float32)/255.0
    out01 = pipeline(src01, adj, fast_mode=fast_mode)
    return (np.clip(out01,0,1)*255.0 + 0.5).astype(np.uint8)

def apply_transforms(arr_u8, adj):
    """ใช้ทรานส์ฟอร์ม (หมุน/กลับ/ครอป) หลังแต่งภาพเสร็จ"""
    out = arr_u8
    # rotate (รองรับ 0/90/180/270 ได้ทันที, องศาอื่นจะใช้ PIL)
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
    ext=os.path.splitext(path)[1].lower()
    if ext in (".jpg",".jpeg",".png",".tif",".tiff"):
        img=Image.open(path).convert("RGB")
        full=np.array(img,dtype=np.uint8)
    elif rawpy is not None:
        with rawpy.imread(path) as raw:
            full=raw.postprocess(use_camera_wb=True,no_auto_bright=True,output_bps=8)
    else:
        raise RuntimeError("RAW file needs rawpy. Install: pip install rawpy")

    thumb=Image.fromarray(full).copy()
    thumb.thumbnail(thumb_size, Image.BILINEAR)
    thumb=np.array(thumb,dtype=np.uint8)
    return full, thumb
