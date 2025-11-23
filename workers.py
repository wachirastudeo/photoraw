import os
import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal, QRunnable, QMutex
from imaging import decode_image, pipeline, apply_transforms, preview_sharpen, process_image_fast

class DecodeSignals(QObject):
    done=Signal(dict); error=Signal(str)

class DecodeWorker(QRunnable):
    def __init__(self, path, thumb_w=72, thumb_h=48):
        super().__init__()
        self.path=path; self.thumb_w=thumb_w; self.thumb_h=thumb_h
        self.signals=DecodeSignals()
        # Prevent the QRunnable from being auto-deleted before signals are emitted
        self.setAutoDelete(False)
    def run(self):
        try:
            full, thumb = decode_image(self.path, (self.thumb_w, self.thumb_h))
            self.signals.done.emit({"name":self.path,"full":full,"thumb":thumb})
        except Exception as e:
            self.signals.error.emit(f"Decode error: {self.path}\n{e}")

class PreviewSignals(QObject):
    ready=Signal(np.ndarray)

class PreviewWorker(QRunnable):
    _mutex = QMutex()
    _latest_id = 0

    def __init__(self, full_rgb, adj, long_edge, sharpen_amt, mode, req_id, live=False, base_override=None, is_zoomed=False, zoom_point=None, preview_size=None, processed_cache=None, low_spec=False):
        super().__init__()
        self.full_rgb=full_rgb
        self.adj=adj
        self.long_edge=long_edge
        self.sharpen_amt=sharpen_amt
        self.mode = mode  # "single" หรือ "split"
        self.req_id=req_id
        self.live = live  # ถ้าลาก slider อยู่ ใช้พรีวิวเบา
        self.base_override = base_override  # ใช้ภาพที่ resize มาแล้ว ถ้ามี
        self.is_zoomed = is_zoomed
        self.zoom_point = zoom_point
        self.preview_size = preview_size
        self.processed_cache = processed_cache or {}
        self.low_spec = low_spec
        self.signals=PreviewSignals()
        # Prevent the QRunnable from being auto-deleted before signals are emitted
        self.setAutoDelete(False)

    @classmethod
    def next_id(cls):
        cls._mutex.lock(); cls._latest_id += 1; rid = cls._latest_id; cls._mutex.unlock(); return rid
    @classmethod
    def is_stale(cls, rid):
        cls._mutex.lock(); stale = rid < cls._latest_id; cls._mutex.unlock(); return stale

    def _resize_long(self, arr, long_edge):
        h,w,_=arr.shape; cur=max(h,w)
        if cur<=long_edge: return arr
        s=long_edge/float(cur); nw,nh=int(w*s),int(h*s)
        return np.array(Image.fromarray(arr).resize((nw,nh), Image.BILINEAR), dtype=np.uint8)

    def run(self):
        if PreviewWorker.is_stale(self.req_id): return

        if self.is_zoomed and self.mode == "single":
            # ... (Zoom logic remains same) ...
            # OPTIMIZATION: Crop-then-Process approach
            # Instead of processing the full image (slow with effects), we:
            # 1. Apply geometric transforms (Rotate/Flip/Crop) to the raw image
            # 2. Crop the visible area
            # 3. Process only the cropped patch
            
            # 1. Get Geometrically Transformed Raw (Cached)
            # We only care about geometric settings for this cache
            geo_keys = ["rotate", "flip_h", "crop"]
            geo_settings = {k: self.adj.get(k) for k in geo_keys}
            geo_hash = str(sorted(geo_settings.items()))
            zoom_geo_cache_key = ("zoom_geo_raw", geo_hash)
            
            if zoom_geo_cache_key in self.processed_cache:
                transformed_raw = self.processed_cache[zoom_geo_cache_key]
            else:
                # Apply transforms to raw image (disable export sharpen for this step)
                geo_adj = self.adj.copy()
                geo_adj["export_sharpen"] = 0.0
                transformed_raw = apply_transforms(self.full_rgb, geo_adj)
                self.processed_cache[zoom_geo_cache_key] = transformed_raw
            
            # 2. Calculate Crop Coordinates
            h_full, w_full, _ = transformed_raw.shape
            preview_w, preview_h = self.preview_size.width(), self.preview_size.height()

            crop_w, crop_h = preview_w, preview_h
            center_x = self.zoom_point.x() * w_full
            center_y = self.zoom_point.y() * h_full

            x0 = int(round(center_x - crop_w / 2))
            y0 = int(round(center_y - crop_h / 2))

            # Clamp to image boundaries
            x0 = max(0, min(w_full - crop_w, x0))
            y0 = max(0, min(h_full - crop_h, y0))
            
            # Crop the raw patch
            raw_patch = transformed_raw[y0:y0+crop_h, x0:x0+crop_w].copy()
            
            # 3. Process the Patch
            # Disable vignette for patch processing to avoid mini-vignette
            patch_adj = self.adj.copy()
            patch_adj["vignette"] = 0.0
            
            # Process color/effects on the small patch (Fast!)
            out = process_image_fast(raw_patch, patch_adj, fast_mode=False)
            
            # Apply preview sharpening
            out = preview_sharpen(out, self.sharpen_amt)
            
            if PreviewWorker.is_stale(self.req_id): return
            self.signals.ready.emit(out)
            return
        else:
            # Normal preview logic
            target_long_edge = self.long_edge
            
            # Aggressive downsampling for live preview in low spec mode
            if self.live and self.low_spec:
                target_long_edge = max(320, self.long_edge // 2)
            
            base = self.base_override if self.base_override is not None else self._resize_long(self.full_rgb, target_long_edge)

        if self.mode == "split":
            # copy to keep base intact
            base_local = base
            b = apply_transforms(base.copy(), self.adj)
            # AFTER: แต่งสี + transforms
            # AFTER: แต่งสี + transforms
            # src01 = base_local.astype(np.float32)/255.0
            # after01 = pipeline(src01, self.adj, fast_mode=self.live)
            # a = (np.clip(after01,0,1)*255.0 + 0.5).astype(np.uint8)
            a = process_image_fast(base_local, self.adj, fast_mode=self.live)
            a = apply_transforms(a, self.adj)

            if not self.live:
                b = preview_sharpen(b, self.sharpen_amt)
                a = preview_sharpen(a, self.sharpen_amt)
            else:
                # Apply sharpening even in live mode for better perceived quality
                # It's a simple 3x3 convolution on a resized image, so it should be fast enough
                b = preview_sharpen(b, self.sharpen_amt)
                a = preview_sharpen(a, self.sharpen_amt)

            h = min(b.shape[0], a.shape[0])
            if b.shape[0]!=h: b = np.array(Image.fromarray(b).resize((b.shape[1], h), Image.BILINEAR))
            if a.shape[0]!=h: a = np.array(Image.fromarray(a).resize((a.shape[1], h), Image.BILINEAR))
            out = np.concatenate([b, a], axis=1)
            if PreviewWorker.is_stale(self.req_id): return
            self.signals.ready.emit(out)
            return

        # โหมดปกติ: AFTER อย่างเดียว
        # โหมดปกติ: AFTER อย่างเดียว
        # src01 = base.astype(np.float32)/255.0
        # out01 = pipeline(src01, self.adj, fast_mode=self.live)
        # out   = (np.clip(out01,0,1)*255.0 + 0.5).astype(np.uint8)
        out = process_image_fast(base, self.adj, fast_mode=self.live)
        out = apply_transforms(out, self.adj)
        
        # Apply sharpening in live mode too
        out = preview_sharpen(out, self.sharpen_amt)
            
        if PreviewWorker.is_stale(self.req_id): return
        self.signals.ready.emit(out)

class ExportSignals(QObject):
    progress=Signal(int,int); done=Signal(str); error=Signal(str)

class ExportWorker(QRunnable):
    def __init__(self, items, out_dir, opts):
        super().__init__()
        self.items=items; self.out_dir=out_dir; self.opts=opts
        self.signals=ExportSignals()
        # Prevent the QRunnable from being auto-deleted before signals are emitted
        self.setAutoDelete(False)

    def _resize_long_edge(self, arr, long_edge):
        if not long_edge or long_edge<=0: return arr
        from PIL import Image
        h,w,_=arr.shape; cur=max(h,w)
        if cur<=long_edge: return arr
        s=long_edge/float(cur); nw,nh=int(w*s),int(h*s)
        return np.array(Image.fromarray(arr).resize((nw,nh), Image.LANCZOS), dtype=np.uint8)

    def run(self):
        try:
            total=len(self.items)
            from PIL import Image
            fmt=self.opts.get("fmt","JPEG").upper()
            quality=int(self.opts.get("quality",92))
            progressive=bool(self.opts.get("progressive",True))
            optimize=bool(self.opts.get("optimize",True))
            long_edge=self.opts.get("long_edge",None)
            naming_mode = self.opts.get("naming_mode", "Original Name")
            custom_text = self.opts.get("custom_text", "Photo")
            start_num = int(self.opts.get("start_num", 1))
            limit_size_kb = int(self.opts.get("limit_size_kb", 0))
            
            for i,it in enumerate(self.items, start=1):
                # full01=it["full"].astype(np.float32)/255.0
                # out01=pipeline(full01, it["settings"])
                # out=(np.clip(out01,0,1)*255.0 + 0.5).astype(np.uint8)
                out = process_image_fast(it["full"], it["settings"])
                out=apply_transforms(out, it["settings"])
                out=self._resize_long_edge(out, long_edge)
                
                # Determine filename
                if naming_mode == "Custom Name + Sequence":
                    # Use sequence number: start_num + current index (0-based)
                    seq = start_num + (i - 1)
                    filename = f"{custom_text}-{seq:03d}"
                else:
                    base=os.path.splitext(os.path.basename(it["name"]))[0]
                    filename = f"{base}{suffix}"
                
                out_path = os.path.join(self.out_dir, filename)
                
                if fmt=="PNG":
                    Image.fromarray(out).save(f"{out_path}.png","PNG",compress_level=6,optimize=True)
                else:
                    # JPEG with optional size limit
                    save_kwargs = {
                        "quality": max(1,min(100,quality)),
                        "progressive": progressive,
                        "optimize": optimize,
                        "subsampling": "4:2:0"
                    }
                    
                    if limit_size_kb > 0:
                        # Try to fit within limit
                        target_bytes = limit_size_kb * 1024
                        img_pil = Image.fromarray(out)
                        
                        # Binary search for quality if needed, or just iterative
                        # Simple approach: Try current quality, if too big, reduce.
                        
                        import io
                        buf = io.BytesIO()
                        img_pil.save(buf, "JPEG", **save_kwargs)
                        size = buf.tell()
                        
                        if size > target_bytes:
                            # Reduce quality
                            q_min, q_max = 1, quality
                            best_q = 1
                            
                            # Binary search
                            while q_min <= q_max:
                                q_mid = (q_min + q_max) // 2
                                buf.seek(0); buf.truncate(0)
                                save_kwargs["quality"] = q_mid
                                img_pil.save(buf, "JPEG", **save_kwargs)
                                size = buf.tell()
                                
                                if size <= target_bytes:
                                    best_q = q_mid
                                    q_min = q_mid + 1
                                else:
                                    q_max = q_mid - 1
                            
                            # Save with best quality found
                            save_kwargs["quality"] = best_q
                            # If best_q is 1 and still too big, we just save it (can't do much more without resize)
                    
                    Image.fromarray(out).save(f"{out_path}.jpg","JPEG", **save_kwargs)
                self.signals.progress.emit(i,total)
            self.signals.done.emit(self.out_dir)
        except Exception as e:
            self.signals.error.emit(str(e))
