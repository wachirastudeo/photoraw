use std::collections::HashMap;
use rayon::prelude::*;

// Helper functions
#[inline(always)]
fn clamp01(x: f32) -> f32 {
    x.max(0.0).min(1.0)
}

#[inline(always)]
fn rgb_to_lum(r: f32, g: f32, b: f32) -> f32 {
    0.2126 * r + 0.7152 * g + 0.0722 * b
}

#[inline(always)]
fn rgb_to_hsv(r: f32, g: f32, b: f32) -> (f32, f32, f32) {
    let max = r.max(g).max(b);
    let min = r.min(g).min(b);
    let d = max - min;
    let mut h = 0.0;
    let s = if max == 0.0 { 0.0 } else { d / max };
    let v = max;

    if d > 1e-6 {
        if max == r {
            h = (g - b) / d + (if g < b { 6.0 } else { 0.0 });
        } else if max == g {
            h = (b - r) / d + 2.0;
        } else {
            h = (r - g) / d + 4.0;
        }
        h /= 6.0;
    }
    (h * 360.0, s, v)
}

#[inline(always)]
fn hsv_to_rgb(h: f32, s: f32, v: f32) -> (f32, f32, f32) {
    let h = h % 360.0;
    let c = v * s;
    let x = c * (1.0 - ((h / 60.0) % 2.0 - 1.0).abs());
    let m = v - c;
    
    let (r, g, b) = if h < 60.0 {
        (c, x, 0.0)
    } else if h < 120.0 {
        (x, c, 0.0)
    } else if h < 180.0 {
        (0.0, c, x)
    } else if h < 240.0 {
        (0.0, x, c)
    } else if h < 300.0 {
        (x, 0.0, c)
    } else {
        (c, 0.0, x)
    };
    (r + m, g + m, b + m)
}

pub struct ImageSettings {
    pub exposure: f32,
    pub contrast: f32,
    pub highlights: f32,
    pub shadows: f32,
    pub whites: f32,
    pub blacks: f32,
    pub saturation: f32,
    pub vibrance: f32,
    pub temperature: f32,
    pub tint: f32,
    pub gamma: f32,
    pub clarity: f32,
    pub texture: f32,
    pub mid_contrast: f32,
    pub dehaze: f32,
    pub denoise: f32,
    pub vignette: f32,
    pub export_sharpen: f32,
    pub tone_curve: f32,
    // HSL
    pub h_red: f32, pub s_red: f32, pub l_red: f32,
    pub h_orange: f32, pub s_orange: f32, pub l_orange: f32,
    pub h_yellow: f32, pub s_yellow: f32, pub l_yellow: f32,
    pub h_green: f32, pub s_green: f32, pub l_green: f32,
    pub h_aqua: f32, pub s_aqua: f32, pub l_aqua: f32,
    pub h_blue: f32, pub s_blue: f32, pub l_blue: f32,
    pub h_purple: f32, pub s_purple: f32, pub l_purple: f32,
    pub h_magenta: f32, pub s_magenta: f32, pub l_magenta: f32,
}

impl ImageSettings {
    pub fn from_hashmap(map: &HashMap<String, f32>) -> Self {
        let get = |k: &str| *map.get(k).unwrap_or(&0.0);
        Self {
            exposure: get("exposure"),
            contrast: get("contrast"),
            highlights: get("highlights"),
            shadows: get("shadows"),
            whites: get("whites"),
            blacks: get("blacks"),
            saturation: get("saturation"),
            vibrance: get("vibrance"),
            temperature: get("temperature"),
            tint: get("tint"),
            gamma: *map.get("gamma").unwrap_or(&1.0),
            clarity: get("clarity"),
            texture: get("texture"),
            mid_contrast: get("mid_contrast"),
            dehaze: get("dehaze"),
            denoise: get("denoise"),
            vignette: get("vignette"),
            export_sharpen: get("export_sharpen"),
            tone_curve: get("tone_curve"),
            h_red: get("h_red"), s_red: get("s_red"), l_red: get("l_red"),
            h_orange: get("h_orange"), s_orange: get("s_orange"), l_orange: get("l_orange"),
            h_yellow: get("h_yellow"), s_yellow: get("s_yellow"), l_yellow: get("l_yellow"),
            h_green: get("h_green"), s_green: get("s_green"), l_green: get("l_green"),
            h_aqua: get("h_aqua"), s_aqua: get("s_aqua"), l_aqua: get("l_aqua"),
            h_blue: get("h_blue"), s_blue: get("s_blue"), l_blue: get("l_blue"),
            h_purple: get("h_purple"), s_purple: get("s_purple"), l_purple: get("l_purple"),
            h_magenta: get("h_magenta"), s_magenta: get("s_magenta"), l_magenta: get("l_magenta"),
        }
    }
}

pub fn process_pipeline(
    input: &[u8],
    width: usize,
    height: usize,
    settings: &ImageSettings,
    lut: Option<&[u8]>,
) -> Vec<u8> {
    let num_pixels = width * height;
    let mut output = vec![0u8; num_pixels * 3];

    // Pre-calculate constants
    let exposure_mult = 2.0f32.powf(settings.exposure);
    
    let wb_r = 1.0 + 0.8 * settings.temperature - 0.2 * settings.tint;
    let wb_g = 1.0 - 0.1 * settings.temperature + 0.4 * settings.tint;
    let wb_b = 1.0 - 0.8 * settings.temperature - 0.2 * settings.tint;

    let has_hsl = settings.h_red.abs() > 1e-6 || settings.s_red.abs() > 1e-6 || settings.l_red.abs() > 1e-6 ||
                  settings.h_orange.abs() > 1e-6 || settings.s_orange.abs() > 1e-6 || settings.l_orange.abs() > 1e-6 ||
                  settings.h_yellow.abs() > 1e-6 || settings.s_yellow.abs() > 1e-6 || settings.l_yellow.abs() > 1e-6 ||
                  settings.h_green.abs() > 1e-6 || settings.s_green.abs() > 1e-6 || settings.l_green.abs() > 1e-6 ||
                  settings.h_aqua.abs() > 1e-6 || settings.s_aqua.abs() > 1e-6 || settings.l_aqua.abs() > 1e-6 ||
                  settings.h_blue.abs() > 1e-6 || settings.s_blue.abs() > 1e-6 || settings.l_blue.abs() > 1e-6 ||
                  settings.h_purple.abs() > 1e-6 || settings.s_purple.abs() > 1e-6 || settings.l_purple.abs() > 1e-6 ||
                  settings.h_magenta.abs() > 1e-6 || settings.s_magenta.abs() > 1e-6 || settings.l_magenta.abs() > 1e-6;

    // Parallel iteration over pixels
    output.par_chunks_mut(3).enumerate().for_each(|(i, pixel_out)| {
        let idx = i * 3;
        let r0 = input[idx] as f32 / 255.0;
        let g0 = input[idx + 1] as f32 / 255.0;
        let b0 = input[idx + 2] as f32 / 255.0;

        // 1. Exposure
        let mut r = clamp01(r0 * exposure_mult);
        let mut g = clamp01(g0 * exposure_mult);
        let mut b = clamp01(b0 * exposure_mult);

        // 2. White Balance
        r = clamp01(r * wb_r);
        g = clamp01(g * wb_g);
        b = clamp01(b * wb_b);

        // 3. Tone Regions
        let mut lum = rgb_to_lum(r, g, b);
        if settings.shadows.abs() > 1e-6 {
            let w = clamp01(1.0 - (lum * 2.0));
            r = r * (1.0 - w) + (r * (1.0 + 0.8 * settings.shadows)) * w;
            g = g * (1.0 - w) + (g * (1.0 + 0.8 * settings.shadows)) * w;
            b = b * (1.0 - w) + (b * (1.0 + 0.8 * settings.shadows)) * w;
        }
        if settings.highlights.abs() > 1e-6 {
            let t = clamp01(lum * 2.0 - 1.0);
            let w = t * t * (3.0 - 2.0 * t); // Smoothstep
            r = r * (1.0 - w) + (r * (1.0 - 0.8 * settings.highlights)) * w;
            g = g * (1.0 - w) + (g * (1.0 - 0.8 * settings.highlights)) * w;
            b = b * (1.0 - w) + (b * (1.0 - 0.8 * settings.highlights)) * w;
        }
        if settings.whites.abs() > 1e-6 {
            r = (r * (1.0 + settings.whites * 0.6)).min(1.0);
            g = (g * (1.0 + settings.whites * 0.6)).min(1.0);
            b = (b * (1.0 + settings.whites * 0.6)).min(1.0);
        }
        if settings.blacks.abs() > 1e-6 {
            r = (r + settings.blacks * 0.4).max(0.0);
            g = (g + settings.blacks * 0.4).max(0.0);
            b = (b + settings.blacks * 0.4).max(0.0);
        }

        // 4. Dehaze (Pixel-wise part)
        if settings.dehaze.abs() > 1e-6 {
            lum = rgb_to_lum(r, g, b);
            let veil = lum * (0.6 * settings.dehaze);
            r = clamp01(r - veil);
            g = clamp01(g - veil);
            b = clamp01(b - veil);
            // Dehaze adds contrast
            let amount = 0.4 * settings.dehaze;
            r = 0.5 + (r - 0.5) * (1.0 + amount);
            g = 0.5 + (g - 0.5) * (1.0 + amount);
            b = 0.5 + (b - 0.5) * (1.0 + amount);
        }

        // 5. Saturation & Vibrance
        // Python uses mean(axis=2) as gray base, not luminance
        let gray = (r + g + b) / 3.0;
        r = gray + (r - gray) * (1.0 + settings.saturation);
        g = gray + (g - gray) * (1.0 + settings.saturation);
        b = gray + (b - gray) * (1.0 + settings.saturation);
        
        if settings.vibrance.abs() > 1e-6 {
            let sat_now = (r - gray).abs() + (g - gray).abs() + (b - gray).abs();
            let sat_now = sat_now / 3.0; // Mean
            let weight = clamp01(1.0 - sat_now * 2.0);
            r = gray + (r - gray) * (1.0 + settings.vibrance * weight);
            g = gray + (g - gray) * (1.0 + settings.vibrance * weight);
            b = gray + (b - gray) * (1.0 + settings.vibrance * weight);
        }

        // 6. Contrast & Gamma
        if settings.contrast.abs() > 1e-6 {
            r = 0.5 + (r - 0.5) * (1.0 + settings.contrast);
            g = 0.5 + (g - 0.5) * (1.0 + settings.contrast);
            b = 0.5 + (b - 0.5) * (1.0 + settings.contrast);
        }
        if (settings.gamma - 1.0).abs() > 1e-6 {
            let inv_gamma = 1.0 / settings.gamma;
            r = clamp01(r).powf(inv_gamma);
            g = clamp01(g).powf(inv_gamma);
            b = clamp01(b).powf(inv_gamma);
        }

        // 7. Curve LUT
        if let Some(lut_table) = lut {
            if lut_table.len() == 256 {
                let r_idx = (clamp01(r) * 255.0 + 0.5) as usize;
                let g_idx = (clamp01(g) * 255.0 + 0.5) as usize;
                let b_idx = (clamp01(b) * 255.0 + 0.5) as usize;
                
                // Safety check although indices should be 0-255
                r = lut_table[r_idx.min(255)] as f32 / 255.0;
                g = lut_table[g_idx.min(255)] as f32 / 255.0;
                b = lut_table[b_idx.min(255)] as f32 / 255.0;
            }
        }

        // 8. Mid Contrast
        if settings.mid_contrast.abs() > 1e-6 {
            r = clamp01(0.5 + (r - 0.5) * (1.0 + 1.6 * settings.mid_contrast));
            g = clamp01(0.5 + (g - 0.5) * (1.0 + 1.6 * settings.mid_contrast));
            b = clamp01(0.5 + (b - 0.5) * (1.0 + 1.6 * settings.mid_contrast));
        }

        // 8. HSL Mixer
        if has_hsl {
            let (h0, s0, v0) = rgb_to_hsv(r, g, b);
            let (mut h, mut s, mut v) = (h0, s0, v0);
            
            // Helper to apply HSL
            // Use h_orig for weight calculation, h_val/s_val/v_val for modification
            let apply_color = |h_val: f32, s_val: f32, v_val: f32, h_orig: f32, center: f32, dh: f32, ds: f32, dl: f32| -> (f32, f32, f32) {
                let dist = (h_orig - center).abs() % 360.0;
                let d = dist.min(360.0 - dist);
                let w = clamp01(1.0 - (d / 50.0));
                let w = w * w * (3.0 - 2.0 * w); // Smoothstep
                
                let new_h = if dh.abs() > 1e-6 { (h_val + dh * w) % 360.0 } else { h_val };
                let new_s = if ds.abs() > 1e-6 { clamp01(s_val * (1.0 + ds * w)) } else { s_val };
                let new_v = if dl.abs() > 1e-6 { clamp01(v_val + dl * w * 0.5) } else { v_val };
                (new_h, new_s, new_v)
            };

            // Apply for each color (Red, Orange, Yellow, etc.)
            let (h1, s1, v1) = apply_color(h, s, v, h0, 0.0, settings.h_red, settings.s_red, settings.l_red); h=h1; s=s1; v=v1;
            let (h1, s1, v1) = apply_color(h, s, v, h0, 30.0, settings.h_orange, settings.s_orange, settings.l_orange); h=h1; s=s1; v=v1;
            let (h1, s1, v1) = apply_color(h, s, v, h0, 60.0, settings.h_yellow, settings.s_yellow, settings.l_yellow); h=h1; s=s1; v=v1;
            let (h1, s1, v1) = apply_color(h, s, v, h0, 120.0, settings.h_green, settings.s_green, settings.l_green); h=h1; s=s1; v=v1;
            let (h1, s1, v1) = apply_color(h, s, v, h0, 180.0, settings.h_aqua, settings.s_aqua, settings.l_aqua); h=h1; s=s1; v=v1;
            let (h1, s1, v1) = apply_color(h, s, v, h0, 240.0, settings.h_blue, settings.s_blue, settings.l_blue); h=h1; s=s1; v=v1;
            let (h1, s1, v1) = apply_color(h, s, v, h0, 280.0, settings.h_purple, settings.s_purple, settings.l_purple); h=h1; s=s1; v=v1;
            let (h1, s1, v1) = apply_color(h, s, v, h0, 320.0, settings.h_magenta, settings.s_magenta, settings.l_magenta); h=h1; s=s1; v=v1;

            let (r_new, g_new, b_new) = hsv_to_rgb(h, s, v);
            r = r_new; g = g_new; b = b_new;
        }

        // 9. Vignette
        if settings.vignette.abs() > 1e-6 {
            let y_coord = (i / width) as f32;
            let x_coord = (i % width) as f32;
            let cy = (height as f32 - 1.0) / 2.0;
            let cx = (width as f32 - 1.0) / 2.0;
            let ry = cy.max(1.0);
            let rx = cx.max(1.0);
            let dy = (y_coord - cy) / ry;
            let dx = (x_coord - cx) / rx;
            let r2 = dx * dx + dy * dy;
            let mask = clamp01(1.0 - settings.vignette * r2).max(0.2);
            r *= mask;
            g *= mask;
            b *= mask;
        }

        // Final Clamp & Write
        pixel_out[0] = (clamp01(r) * 255.0 + 0.5) as u8;
        pixel_out[1] = (clamp01(g) * 255.0 + 0.5) as u8;
        pixel_out[2] = (clamp01(b) * 255.0 + 0.5) as u8;
    });

    output
}
