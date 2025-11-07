# workers.py
import os
import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal, QRunnable
from imaging import pipeline

class DecodeSignals(QObject):
    done  = Signal(dict)   # {"name", "full", "preview", "thumb"}
    error = Signal(str)

class DecodeWorker(QRunnable):
    def __init__(self, path, preview_max=1600, thumb_w=140, thumb_h=90):
        super().__init__()
        self.path = path
        self.preview_max = preview_max
        self.thumb_w = thumb_w
        self.thumb_h = thumb_h
        self.signals = DecodeSignals()

    def run(self):
        try:
            ext = os.path.splitext(self.path)[1].lower()
            if ext in (".jpg",".jpeg",".png",".tif",".tiff"):
                img = Image.open(self.path).convert("RGB")
                full = np.array(img, dtype=np.uint8)
            else:
                import rawpy
                with rawpy.imread(self.path) as raw:
                    full = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=8)

            # preview
            h,w,_ = full.shape
            scale = min(1.0, self.preview_max / max(h,w))
            if scale < 1.0:
                pw, ph = int(w*scale), int(h*scale)
                preview = np.array(Image.fromarray(full).resize((pw,ph), Image.LANCZOS), dtype=np.uint8)
            else:
                preview = full

            # thumb
            thumb = Image.fromarray(preview).copy()
            thumb.thumbnail((self.thumb_w, self.thumb_h), Image.LANCZOS)
            thumb = np.array(thumb, dtype=np.uint8)

            self.signals.done.emit({"name": self.path, "full": full, "preview": preview, "thumb": thumb})
        except Exception as e:
            self.signals.error.emit(f"Decode error: {self.path}\n{e}")

class ExportSignals(QObject):
    progress = Signal(int, int)  # done, total
    done  = Signal(str)
    error = Signal(str)

class ExportWorker(QRunnable):
    """
    items: list of dict: {name, full(np.uint8 HxWx3), settings}
    opts: {
      "fmt": "JPEG"|"PNG",
      "quality": int(1..100)  (JPEG only),
      "progressive": bool     (JPEG only),
      "optimize": bool,       (JPEG only)
      "long_edge": int|None,  (resize if set)
      "suffix": str
    }
    """
    def __init__(self, items, out_dir, opts):
        super().__init__()
        self.items = items
        self.out_dir = out_dir
        self.opts = opts
        self.signals = ExportSignals()

    def _resize_long_edge(self, arr, long_edge):
        if not long_edge or long_edge <= 0:
            return arr
        h, w, _ = arr.shape
        cur_long = max(h, w)
        if cur_long <= long_edge:
            return arr
        scale = long_edge / float(cur_long)
        new_w, new_h = int(w*scale), int(h*scale)
        return np.array(Image.fromarray(arr).resize((new_w, new_h), Image.LANCZOS), dtype=np.uint8)

    def run(self):
        try:
            total = len(self.items)
            fmt = self.opts.get("fmt", "JPEG").upper()
            quality = int(self.opts.get("quality", 90))
            progressive = bool(self.opts.get("progressive", True))
            optimize = bool(self.opts.get("optimize", True))
            long_edge = self.opts.get("long_edge", None)
            suffix = self.opts.get("suffix", "_edit") or "_edit"

            for i, it in enumerate(self.items, start=1):
                full01 = it["full"].astype(np.float32)/255.0
                adj    = it["settings"]
                out01  = pipeline(full01, adj)
                out    = (np.clip(out01,0,1)*255.0 + 0.5).astype(np.uint8)

                # resize if needed
                out = self._resize_long_edge(out, long_edge)

                base = os.path.splitext(os.path.basename(it["name"]))[0]
                if fmt == "PNG":
                    save_path = os.path.join(self.out_dir, f"{base}{suffix}.png")
                    Image.fromarray(out).save(save_path, "PNG", compress_level=6, optimize=True)
                else:
                    # JPEG
                    save_path = os.path.join(self.out_dir, f"{base}{suffix}.jpg")
                    Image.fromarray(out).save(
                        save_path,
                        "JPEG",
                        quality=max(1, min(100, quality)),
                        progressive=progressive,
                        optimize=optimize,
                        subsampling="4:2:0"  # ขนาดเล็กลง
                    )

                self.signals.progress.emit(i, total)

            self.signals.done.emit(self.out_dir)
        except Exception as e:
            self.signals.error.emit(str(e))
