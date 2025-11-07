# imaging.py
import numpy as np

# ---------------- Defaults ----------------
DEFAULTS = {
    # Basic
    "exposure": 0.0,
    "contrast": 0.0,
    "highlights": 0.0,
    "shadows": 0.0,
    "whites": 0.0,
    "blacks": 0.0,
    "saturation": 0.0,
    "vibrance": 0.0,
    "temperature": 0.0,
    "tint": 0.0,
    "gamma": 1.0,
    "clarity": 0.0,

    # HSL (per-color offsets)
    # Hue shift in degrees (-60..+60), Sat & Lum are multipliers/offsets (-1..+1)
    # Colors: red, orange, yellow, green, aqua, blue, purple, magenta
    **{f"h_{c}": 0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    **{f"s_{c}": 0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    **{f"l_{c}": 0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
}

# ---------------- Utilities ----------------
def clamp01(a):
    return np.clip(a, 0, 1, out=a)

def rgb_to_lum(rgb):
    return 0.2126*rgb[...,0] + 0.7152*rgb[...,1] + 0.0722*rgb[...,2]

def apply_white_balance(rgb, temperature=0.0, tint=0.0):
    r = 1 + 0.8*temperature - 0.2*tint
    g = 1 - 0.1*temperature + 0.4*tint
    b = 1 - 0.8*temperature - 0.2*tint
    out = rgb.copy()
    out[...,0] *= r; out[...,1] *= g; out[...,2] *= b
    return out

def apply_tone_regions(rgb, highlights=0.0, shadows=0.0, whites=0.0, blacks=0.0):
    y = clamp01(rgb_to_lum(rgb))
    out = rgb.copy()
    if abs(shadows) > 1e-6:
        w = np.clip(1.0 - (y*2.0), 0, 1)
        gain = 1.0 + 0.8*shadows
        out = out*(1-w[...,None]) + (out*gain)*w[...,None]
    if abs(highlights) > 1e-6:
        w = np.clip((y*2.0 - 1.0), 0, 1)
        gain = 1.0 - 0.8*highlights
        out = out*(1-w[...,None]) + (out*gain)*w[...,None]
    if abs(whites) > 1e-6:
        out = np.minimum(out*(1.0 + whites*0.6), 1.0)
    if abs(blacks) > 1e-6:
        out = np.maximum(out + blacks*0.4, 0.0)
    return out

def apply_saturation_vibrance(rgb, saturation=0.0, vibrance=0.0):
    gray = rgb.mean(axis=2, keepdims=True)
    out = gray + (rgb - gray) * (1.0 + saturation)
    if abs(vibrance) > 1e-6:
        sat_now = np.maximum(np.abs(rgb - gray), 1e-6).mean(axis=2, keepdims=True)
        weight = np.clip(1.0 - sat_now*2.0, 0, 1)
        out = gray + (out - gray) * (1.0 + vibrance*weight)
    return out

def apply_contrast_gamma(rgb, contrast=0.0, gamma=1.0):
    out = rgb
    if abs(contrast) > 1e-6:
        out = 0.5 + (out - 0.5)*(1.0 + contrast)
    if abs(gamma-1.0) > 1e-6:
        out = np.power(np.clip(out, 0, 1), 1.0/gamma)
    return out

def apply_clarity(rgb, amount=0.0):
    if abs(amount) < 1e-6:
        return rgb
    pad = np.pad(rgb, ((1,1),(1,1),(0,0)), mode='reflect')
    blur = (
        pad[:-2,:-2] + pad[:-2,1:-1] + pad[:-2,2:] +
        pad[1:-1,:-2] + pad[1:-1,1:-1] + pad[1:-1,2:] +
        pad[2:,:-2] + pad[2:,1:-1] + pad[2:,2:]
    ) / 9.0
    high = rgb - blur
    return clamp01(rgb + high*(0.6*amount))

# ---------------- HSL / Color Mixer ----------------
# เราจะใช้ HSV แบบเวคเตอร์ (ใกล้เคียง HSL สำหรับงานปรับสี) เพื่อประสิทธิภาพ
def rgb_to_hsv(rgb):
    r, g, b = rgb[...,0], rgb[...,1], rgb[...,2]
    mx = np.max(rgb, axis=2)
    mn = np.min(rgb, axis=2)
    diff = mx - mn
    # Hue
    h = np.zeros_like(mx)
    mask = diff > 1e-6
    r_eq = (mx == r) & mask
    g_eq = (mx == g) & mask
    b_eq = (mx == b) & mask
    h[r_eq] = (60*((g[r_eq]-b[r_eq])/diff[r_eq]) + 360) % 360
    h[g_eq] = (60*((b[g_eq]-r[g_eq])/diff[g_eq]) + 120) % 360
    h[b_eq] = (60*((r[b_eq]-g[b_eq])/diff[b_eq]) + 240) % 360
    # Sat
    s = np.zeros_like(mx)
    nz = mx > 1e-6
    s[nz] = diff[nz] / mx[nz]
    v = mx
    return h, s, v

def hsv_to_rgb(h, s, v):
    # h in [0,360)
    h = (h % 360) / 60.0
    c = v*s
    x = c*(1 - np.abs(h % 2 - 1))
    m = v - c
    z = np.zeros_like(h)
    # sextants
    conds = [
        ( (0 <= h) & (h < 1), (c,x,z) ),
        ( (1 <= h) & (h < 2), (x,c,z) ),
        ( (2 <= h) & (h < 3), (z,c,x) ),
        ( (3 <= h) & (h < 4), (z,x,c) ),
        ( (4 <= h) & (h < 5), (x,z,c) ),
        ( (5 <= h) & (h < 6), (c,z,x) ),
    ]
    r = np.zeros_like(h); g = np.zeros_like(h); b = np.zeros_like(h)
    for mask, (rr,gg,bb) in conds:
        r[mask] = rr[mask]; g[mask] = gg[mask]; b[mask] = bb[mask]
    rgb = np.stack([r+m, g+m, b+m], axis=-1)
    return rgb

# น้ำหนักสีแต่ละกลุ่มตาม Hue (ศูนย์กลาง + ช่วงกว้างแบบนุ่ม ๆ)
_COLOR_CENTERS = {
    "red": 0.0, "orange": 30.0, "yellow": 60.0, "green": 120.0,
    "aqua": 180.0, "blue": 240.0, "purple": 280.0, "magenta": 320.0
}
# ความกว้างคร่าว ๆ (deg); ใช้ระยะเชิงวงกลม แล้วทำ weight แบบ smooth
_COLOR_WIDTH = 50.0

def _circular_distance_deg(a, b):
    d = np.abs(a - b) % 360.0
    return np.minimum(d, 360.0 - d)

def _color_weight(h, center, width=_COLOR_WIDTH):
    d = _circular_distance_deg(h, center)
    # smooth weight: 1 at center, ~0 at ~width
    w = np.clip(1.0 - (d/width), 0.0, 1.0)
    # soften edge
    return w*w*(3 - 2*w)  # smoothstep

def apply_hsl_mixer(rgb, adj):
    # Convert to HSV
    h, s, v = rgb_to_hsv(rgb)
    h_new = h.copy()
    s_new = s.copy()
    v_new = v.copy()

    for name, center in _COLOR_CENTERS.items():
        w = _color_weight(h, center)
        # hue shift in degrees (-60..+60)
        dh = float(adj.get(f"h_{name}", 0.0))
        if abs(dh) > 1e-6:
            h_new = (h_new + dh*w) % 360.0
        # saturation delta (-1..+1): scale away/toward gray
        ds = float(adj.get(f"s_{name}", 0.0))
        if abs(ds) > 1e-6:
            # multiply relative to 1.0 with weight
            s_new = np.clip(s_new * (1.0 + ds*w), 0.0, 1.0)
        # luminance/brightness delta (-1..+1): adjust v
        dl = float(adj.get(f"l_{name}", 0.0))
        if abs(dl) > 1e-6:
            v_new = np.clip(v_new + dl*w*0.5, 0.0, 1.0)

    out = hsv_to_rgb(h_new, s_new, v_new)
    return out

# ---------------- Pipeline ----------------
def pipeline(rgb01, adj):
    exp   = adj["exposure"];   con  = adj["contrast"];   gam = adj["gamma"]
    hi    = adj["highlights"]; sh   = adj["shadows"];    wh  = adj["whites"]; bl = adj["blacks"]
    sat   = adj["saturation"]; vib  = adj["vibrance"]
    tmp   = adj["temperature"]; tnt = adj["tint"]
    clr   = adj["clarity"]

    x = clamp01(rgb01 * (2.0 ** exp))
    x = clamp01(apply_white_balance(x, tmp, tnt))
    x = clamp01(apply_tone_regions(x, hi, sh, wh, bl))
    x = clamp01(apply_saturation_vibrance(x, sat, vib))
    x = clamp01(apply_contrast_gamma(x, con, gam))
    x = clamp01(apply_clarity(x, clr))

    # Color Mixer (HSL-like)
    x = clamp01(apply_hsl_mixer(x, adj))
    return x
