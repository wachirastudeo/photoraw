# app.py — RAW Mini Editor (HSL Colored, Persistent Catalog, Split Before/After)
import os, sys, json
import numpy as np
from pathlib import Path
from PIL import Image

# RAW optional
try:
    import rawpy
except Exception:
    rawpy = None

from PySide6.QtCore import Qt, QTimer, QThreadPool, QSize, QLocale, QObject, Signal, QRunnable, QMutex
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QFormLayout, QMessageBox, QComboBox, QProgressDialog,
    QFrame, QDialog, QDialogButtonBox, QSpinBox, QCheckBox, QLineEdit,
    QListWidget, QListWidgetItem, QAbstractItemView, QTabWidget, QSlider, QToolButton
)
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QIcon

# ---------------- Persistent catalog ----------------
CATALOG_PATH = Path.home() / ".rawmini_catalog.json"

def load_catalog():
    if CATALOG_PATH.exists():
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_catalog(catalog: dict):
    try:
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_catalog error:", e)

# ---------------- Imaging (เบา + เร็ว) ----------------
def clamp01(a): return np.clip(a, 0, 1, out=a)

DEFAULTS = {
    "exposure":0.0,"contrast":0.0,"highlights":0.0,"shadows":0.0,"whites":0.0,"blacks":0.0,
    "saturation":0.0,"vibrance":0.0,"temperature":0.0,"tint":0.0,"gamma":1.0,"clarity":0.0,
    **{f"h_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    **{f"s_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
    **{f"l_{c}":0.0 for c in ["red","orange","yellow","green","aqua","blue","purple","magenta"]},
}
_COLORS = ["red","orange","yellow","green","aqua","blue","purple","magenta"]
_COLOR_CENTERS = {"red":0.0,"orange":30.0,"yellow":60.0,"green":120.0,"aqua":180.0,"blue":240.0,"purple":280.0,"magenta":320.0}
_COLOR_LABEL = {c:c.capitalize() for c in _COLORS}
_COLOR_SWATCH = {
    "red":"#e53935","orange":"#fb8c00","yellow":"#fdd835","green":"#43a047",
    "aqua":"#26c6da","blue":"#1e88e5","purple":"#8e24aa","magenta":"#d81b60"
}
_COLOR_WIDTH = 50.0

def rgb_to_lum(rgb): return 0.2126*rgb[...,0] + 0.7152*rgb[...,1] + 0.0722*rgb[...,2]
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
def apply_clarity(rgb, amount=0.0):
    if abs(amount)<1e-6: return rgb
    pad=np.pad(rgb,((1,1),(1,1),(0,0)),mode='edge')
    blur=(pad[:-2,:-2]+pad[:-2,1:-1]+pad[:-2,2:]+pad[1:-1,:-2]+pad[1:-1,1:-1]+pad[1:-1,2:]+pad[2:,:-2]+pad[2:,1:-1]+pad[2:,2:])/9.0
    return clamp01(rgb+(rgb-blur)*(0.45*amount))

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

def _circ_dist(a,b): d=np.abs(a-b)%360.0; return np.minimum(d,360.0-d)
def _color_weight(h, center, width=_COLOR_WIDTH):
    d=_circ_dist(h,center); w=np.clip(1.0-(d/width),0,1); return w*w*(3-2*w)
def apply_hsl_mixer(rgb, adj):
    h,s,v=rgb_to_hsv(rgb); hn, sn, vn = h.copy(), s.copy(), v.copy()
    for name,center in _COLOR_CENTERS.items():
        w=_color_weight(h,center)
        dh=float(adj.get(f"h_{name}",0.0)); ds=float(adj.get(f"s_{name}",0.0)); dl=float(adj.get(f"l_{name}",0.0))
        if abs(dh)>1e-6: hn=(hn+dh*w)%360.0
        if abs(ds)>1e-6: sn=np.clip(sn*(1.0+ds*w),0,1)
        if abs(dl)>1e-6: vn=np.clip(vn+dl*w*0.5,0,1)
    return hsv_to_rgb(hn,sn,vn)

def pipeline(rgb01, adj):
    x=clamp01(rgb01*(2.0**adj["exposure"]))
    x=clamp01(apply_white_balance(x,adj["temperature"],adj["tint"]))
    x=clamp01(apply_tone_regions(x,adj["highlights"],adj["shadows"],adj["whites"],adj["blacks"]))
    x=clamp01(apply_saturation_vibrance(x,adj["saturation"],adj["vibrance"]))
    x=clamp01(apply_contrast_gamma(x,adj["contrast"],adj["gamma"]))
    x=clamp01(apply_clarity(x,adj["clarity"]))
    x=clamp01(apply_hsl_mixer(x,adj))
    return x

# --------- Preview sharpening (เฉพาะตอนแสดง) ----------
def preview_sharpen(arr_u8, amount):
    if amount <= 1e-6: return arr_u8
    arr = arr_u8.astype(np.float32)/255.0
    pad=np.pad(arr,((1,1),(1,1),(0,0)),mode='edge')
    blur=(pad[:-2,:-2]+pad[:-2,1:-1]+pad[:-2,2:]+pad[1:-1,:-2]+pad[1:-1,1:-1]+pad[1:-1,2:]+pad[2:,:-2]+pad[2:,1:-1]+pad[2:,2:])/9.0
    out = clamp01(arr + (arr - blur) * (0.8*amount))
    return (out*255.0+0.5).astype(np.uint8)

# ---------------- Workers ----------------
class DecodeSignals(QObject):
    done=Signal(dict); error=Signal(str)

class DecodeWorker(QRunnable):
    def __init__(self, path, thumb_w=72, thumb_h=48):
        super().__init__()
        self.path=path; self.thumb_w=thumb_w; self.thumb_h=thumb_h
        self.signals=DecodeSignals()
    def run(self):
        try:
            ext=os.path.splitext(self.path)[1].lower()
            if ext in (".jpg",".jpeg",".png",".tif",".tiff"):
                img=Image.open(self.path).convert("RGB")
                full=np.array(img,dtype=np.uint8)
            elif rawpy is not None:
                with rawpy.imread(self.path) as raw: full=raw.postprocess(use_camera_wb=True,no_auto_bright=True,output_bps=8)
            else:
                raise RuntimeError("RAW file needs rawpy. Install: pip install rawpy")

            thumb=Image.fromarray(full).copy()
            thumb.thumbnail((self.thumb_w,self.thumb_h), Image.BILINEAR)
            thumb=np.array(thumb,dtype=np.uint8)

            self.signals.done.emit({"name":self.path,"full":full,"thumb":thumb})
        except Exception as e:
            self.signals.error.emit(f"Decode error: {self.path}\n{e}")

class PreviewSignals(QObject):
    ready=Signal(np.ndarray)

class PreviewWorker(QRunnable):
    _mutex = QMutex()
    _latest_id = 0

    def __init__(self, full_rgb, adj, long_edge, sharpen_amt, mode, req_id):
        super().__init__()
        self.full_rgb=full_rgb
        self.adj=adj
        self.long_edge=long_edge
        self.sharpen_amt=sharpen_amt
        self.mode = mode  # "single" หรือ "split"
        self.req_id=req_id
        self.signals=PreviewSignals()

    @classmethod
    def next_id(cls):
        cls._mutex.lock(); cls._latest_id += 1; rid = cls._latest_id; cls._mutex.unlock(); return rid
    @classmethod
    def is_stale(cls, rid):
        cls._mutex.lock(); stale = rid < cls._latest_id; cls._mutex.unlock(); return stale

    def run(self):
        if PreviewWorker.is_stale(self.req_id): return

        def _resize_long(arr, long_edge):
            h,w,_=arr.shape; cur=max(h,w)
            if cur<=long_edge: return arr
            s=long_edge/float(cur); nw,nh=int(w*s),int(h*s)
            return np.array(Image.fromarray(arr).resize((nw,nh), Image.BILINEAR), dtype=np.uint8)

        if self.mode == "split":
            base = _resize_long(self.full_rgb, self.long_edge)
            before_u8 = base
            src01 = base.astype(np.float32)/255.0
            after01 = pipeline(src01, self.adj)
            after_u8 = (np.clip(after01,0,1)*255.0 + 0.5).astype(np.uint8)

            before_u8 = preview_sharpen(before_u8, self.sharpen_amt)
            after_u8  = preview_sharpen(after_u8,  self.sharpen_amt)

            h1,w1,_=before_u8.shape; h2,w2,_=after_u8.shape
            h=min(h1,h2)
            if h1!=h:
                before_u8 = np.array(Image.fromarray(before_u8).resize((w1, h), Image.BILINEAR))
            if h2!=h:
                after_u8  = np.array(Image.fromarray(after_u8 ).resize((w2, h), Image.BILINEAR))
            out = np.concatenate([before_u8, after_u8], axis=1)
            if PreviewWorker.is_stale(self.req_id): return
            self.signals.ready.emit(out)
            return

        # โหมดปกติ: single (After อย่างเดียว)
        base = _resize_long(self.full_rgb, self.long_edge)
        src01 = base.astype(np.float32)/255.0
        out01 = pipeline(src01, self.adj)
        out   = (np.clip(out01,0,1)*255.0 + 0.5).astype(np.uint8)
        out   = preview_sharpen(out, self.sharpen_amt)
        if PreviewWorker.is_stale(self.req_id): return
        self.signals.ready.emit(out)

class ExportSignals(QObject):
    progress=Signal(int,int); done=Signal(str); error=Signal(str)

class ExportWorker(QRunnable):
    def __init__(self, items, out_dir, opts):
        super().__init__()
        self.items=items; self.out_dir=out_dir; self.opts=opts
        self.signals=ExportSignals()
    def _resize_long_edge(self, arr, long_edge):
        if not long_edge or long_edge<=0: return arr
        h,w,_=arr.shape; cur=max(h,w)
        if cur<=long_edge: return arr
        s=long_edge/float(cur); nw,nh=int(w*s),int(h*s)
        return np.array(Image.fromarray(arr).resize((nw,nh), Image.LANCZOS), dtype=np.uint8)
    def run(self):
        try:
            total=len(self.items)
            fmt=self.opts.get("fmt","JPEG").upper()
            quality=int(self.opts.get("quality",92))
            progressive=bool(self.opts.get("progressive",True))
            optimize=bool(self.opts.get("optimize",True))
            long_edge=self.opts.get("long_edge",None)
            suffix=self.opts.get("suffix","_edit") or "_edit"
            for i,it in enumerate(self.items, start=1):
                full01=it["full"].astype(np.float32)/255.0
                out01=pipeline(full01, it["settings"])
                out=(np.clip(out01,0,1)*255.0 + 0.5).astype(np.uint8)
                out=self._resize_long_edge(out, long_edge)
                base=os.path.splitext(os.path.basename(it["name"]))[0]
                if fmt=="PNG":
                    Image.fromarray(out).save(os.path.join(self.out_dir, f"{base}{suffix}.png"),"PNG",compress_level=6,optimize=True)
                else:
                    Image.fromarray(out).save(os.path.join(self.out_dir, f"{base}{suffix}.jpg"),"JPEG",
                        quality=max(1,min(100,quality)), progressive=progressive, optimize=optimize, subsampling="4:2:0")
                self.signals.progress.emit(i,total)
            self.signals.done.emit(self.out_dir)
        except Exception as e:
            self.signals.error.emit(str(e))

# ---------------- UI helpers ----------------
def colored_slider_style(hex_color: str):
    return f"""
    QSlider::groove:horizontal {{ height: 6px; background: #e6e9ee; border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {hex_color}; height: 6px; border-radius: 3px; }}
    QSlider::add-page:horizontal {{ background: #e6e9ee; height: 6px; border-radius: 3px; }}
    QSlider::handle:horizontal {{
        background: {hex_color}; border: 1px solid rgba(0,0,0,0.15);
        width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;
    }}
    """

def add_slider(form: QFormLayout, title_widget, key: str, lo: float, hi: float, val: float, step=0.01,
               on_change=None, on_reset=None, color_hex=None):
    row = QHBoxLayout(); row.setContentsMargins(0,0,0,0)
    sld = QSlider(Qt.Horizontal)
    sld.setMinimum(int(lo/step)); sld.setMaximum(int(hi/step)); sld.setValue(int(val/step))
    sld.setSingleStep(1); sld.setPageStep(5); sld.setTracking(False)
    if color_hex: sld.setStyleSheet(colored_slider_style(color_hex))
    lab = QLabel(f"{val:.2f}")
    sld.valueChanged.connect(lambda v: (lab.setText(f"{v*step:.2f}"), on_change and on_change(key, v*step)))
    btn = QToolButton(); btn.setText("↺"); btn.setToolTip("Reset")
    btn.clicked.connect(lambda: (sld.blockSignals(True), sld.setValue(int(val/step)), sld.blockSignals(False), on_reset and on_reset(key)))
    row.addWidget(sld); row.addWidget(lab); row.addWidget(btn)
    form.addRow(title_widget, row)
    return sld, lab

def create_chip(color_hex: str, text: str):
    box = QHBoxLayout(); box.setContentsMargins(0,0,0,0); box.setSpacing(6)
    sw = QFrame(); sw.setFixedSize(14,14); sw.setStyleSheet(f"QFrame{{background:{color_hex}; border-radius:3px; border:1px solid #bbb;}}")
    lab = QLabel(text)
    w = QWidget(); w.setLayout(box)
    box.addWidget(sw); box.addWidget(lab); box.addStretch(1)
    return w

def create_filmstrip(icon_size=QSize(72,48), height=68):
    lw=QListWidget(); lw.setViewMode(QListWidget.IconMode); lw.setMovement(QListWidget.Static)
    lw.setFlow(QListWidget.LeftToRight); lw.setWrapping(False); lw.setResizeMode(QListWidget.Adjust)
    lw.setIconSize(icon_size); lw.setFixedHeight(height); lw.setSpacing(6)
    lw.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded); lw.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    lw.setSelectionMode(QAbstractItemView.ExtendedSelection); return lw

def filmstrip_add_item(listwidget: QListWidget, thumb_pixmap: QPixmap, userdata):
    it=QListWidgetItem(""); it.setIcon(QIcon(thumb_pixmap)); it.setData(Qt.UserRole, userdata); listwidget.addItem(it)

def badge_star(pixmap: QPixmap, starred: bool) -> QPixmap:
    if not starred: return pixmap
    pm=QPixmap(pixmap); p=QPainter(pm); p.setRenderHint(QPainter.Antialiasing, True)
    r=12; p.setBrush(QColor(255,215,0)); p.setPen(Qt.NoPen); p.drawEllipse(3,3,r,r)
    p.setPen(QColor(30,30,30)); font=QFont(); font.setPointSize(8); font.setBold(True); p.setFont(font)
    p.drawText(3,3,r,r,Qt.AlignCenter,"★"); p.end(); return pm

# ---------------- Export Dialog ----------------
class ExportOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Export Options")
        lay=QVBoxLayout(self); form=QFormLayout()

        self.cmb_fmt=QComboBox(); self.cmb_fmt.addItems(["JPEG","PNG"]); form.addRow("Format", self.cmb_fmt)
        rowQ=QHBoxLayout(); self.sp_quality=QSpinBox(); self.sp_quality.setRange(1,100); self.sp_quality.setValue(92)
        self.chk_prog=QCheckBox("Progressive"); self.chk_prog.setChecked(True)
        self.chk_opt=QCheckBox("Optimize"); self.chk_opt.setChecked(True)
        rowQ.addWidget(self.sp_quality); rowQ.addWidget(self.chk_prog); rowQ.addWidget(self.chk_opt)
        form.addRow("JPEG Quality", rowQ)

        rowL=QHBoxLayout(); self.cmb_long=QComboBox()
        self.cmb_long.addItems(["No resize","1200","1600","2048","3840","Custom"])
        self.sp_long=QSpinBox(); self.sp_long.setRange(320,20000); self.sp_long.setValue(2048); self.sp_long.setEnabled(False)
        rowL.addWidget(self.cmb_long); rowL.addWidget(self.sp_long); form.addRow("Long Edge", rowL)

        self.ed_suffix=QLineEdit("_edit"); form.addRow("Suffix", self.ed_suffix)
        lay.addLayout(form)

        def on_fmt():
            isjpg=self.cmb_fmt.currentText()=="JPEG"
            self.sp_quality.setEnabled(isjpg); self.chk_prog.setEnabled(isjpg); self.chk_opt.setEnabled(isjpg)
        self.cmb_fmt.currentTextChanged.connect(lambda _: on_fmt()); on_fmt()
        self.cmb_long.currentTextChanged.connect(lambda _: self.sp_long.setEnabled(self.cmb_long.currentText()=="Custom"))

        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); lay.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

    def get_options(self):
        fmt=self.cmb_fmt.currentText(); sel=self.cmb_long.currentText()
        long_edge=None if sel=="No resize" else (int(self.sp_long.value()) if sel=="Custom" else int(sel))
        return {
            "fmt":fmt,"quality":int(self.sp_quality.value()),
            "progressive":bool(self.chk_prog.isChecked()),"optimize":bool(self.chk_opt.isChecked()),
            "long_edge":long_edge,"suffix":self.ed_suffix.text().strip() or "_edit"
        }

# ---------------- Main ----------------
class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAW Mini Editor — with Catalog & Split Before/After")
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
        self.pool=QThreadPool.globalInstance()

        # state
        self.items=[]; self.current=-1; self.before=False; self.view_filter="All"
        self.split_mode = False  # โหมด Before/After แบบซ้าย-ขวา
        self.sliders={}
        self.to_load=0; self.loaded=0
        self.expdlg=None; self.last_export_opts=None

        self.catalog = load_catalog()

        # UI root
        root=QVBoxLayout(self)

        # top bar 1
        bar1=QHBoxLayout()
        btnOpen=QPushButton("Open"); btnOpen.clicked.connect(self.open_files)
        btnDelete=QPushButton("Delete Selected"); btnDelete.clicked.connect(self.delete_selected)
        btnStar=QPushButton("Toggle Star"); btnStar.clicked.connect(self.toggle_star_selected)
        self.filterBox=QComboBox(); self.filterBox.addItems(["All","Starred"]); self.filterBox.currentTextChanged.connect(self.apply_filter)

        bar1.addWidget(btnOpen); bar1.addWidget(btnDelete); bar1.addWidget(btnStar)
        bar1.addStretch(1)
        bar1.addWidget(QLabel("Preview Size"))
        self.cmb_prev = QComboBox(); self.cmb_prev.addItems(["540","720","900","1200"]); self.cmb_prev.setCurrentText("900")
        bar1.addWidget(self.cmb_prev)
        bar1.addSpacing(12); bar1.addWidget(QLabel("Sharpness"))
        self.cmb_sharp = QComboBox(); self.cmb_sharp.addItems(["0.00","0.15","0.30","0.45","0.60","0.80","1.00"])
        self.cmb_sharp.setCurrentText("0.30")
        bar1.addStretch(1)
        bar1.addWidget(QLabel("Filter:")); bar1.addWidget(self.filterBox)
        root.addLayout(bar1)

        # จำค่า UI เมื่อเปลี่ยน และรีเฟรชพรีวิว
        self.cmb_prev.currentTextChanged.connect(lambda _ : (self._remember_ui(), self._kick_preview_thread(force=True)))
        self.cmb_sharp.currentTextChanged.connect(lambda _ : (self._remember_ui(), self._kick_preview_thread(force=True)))

        # set UI จากค่าเดิม
        last_ui = self.catalog.get("__ui__", {"preview_size": "900", "sharpness": "0.30"})
        try:
            self.cmb_prev.setCurrentText(last_ui.get("preview_size","900"))
            self.cmb_sharp.setCurrentText(last_ui.get("sharpness","0.30"))
        except Exception:
            pass

        # top bar 2
        bar2=QHBoxLayout()
        btnExportSel=QPushButton("Export Selected"); btnExportSel.clicked.connect(self.export_selected)
        btnExportAll=QPushButton("Export All"); btnExportAll.clicked.connect(self.export_all)
        btnExportFilt=QPushButton("Export (Filtered)"); btnExportFilt.clicked.connect(self.export_filtered)
        btnBA=QPushButton("Before/After (Split)"); btnBA.setCheckable(True)
        btnBA.clicked.connect(self.toggle_split)
        self.btnBA = btnBA
        btnReset=QPushButton("Reset Photo"); btnReset.clicked.connect(self.reset_current)
        bar2.addWidget(btnExportSel); bar2.addWidget(btnExportAll); bar2.addWidget(btnExportFilt); bar2.addStretch(1); bar2.addWidget(btnBA); bar2.addWidget(btnReset)
        root.addLayout(bar2)

        # content
        content=QHBoxLayout()

        # preview
        self.preview=QLabel("Open files to start"); self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(1080, 680); self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setStyleSheet("QLabel{background:#f6f7f9; color:#333; border:1px solid #dfe3e8;}")
        content.addWidget(self.preview, 4)

        # right panel — Tabs
        self.tabs=QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet("""
            QTabWidget::pane{ border:1px solid #dfe3e8; border-radius:8px; background:#fff; }
            QTabBar::tab{ padding:6px 12px; border:1px solid #dfe3e8; border-bottom:none; background:#fafafa; margin-right:4px; border-top-left-radius:6px; border-top-right-radius:6px; }
            QTabBar::tab:selected{ background:#ffffff; }
        """)
        self.tabs.addTab(self.group_basic(), "Basic")
        self.tabs.addTab(self.group_tone(), "Tone")
        self.tabs.addTab(self.group_color(), "Color")
        self.tabs.addTab(self.group_effects(), "Effects")
        self.tabs.addTab(self.group_hsl(), "HSL")
        self.tabs.setFixedWidth(440)
        content.addWidget(self.tabs, 0)
        root.addLayout(content, 1)

        # filmstrip
        self.film=create_filmstrip(QSize(72,48), height=68)
        self.film.itemSelectionChanged.connect(self.on_select_item)
        root.addWidget(self.film)

        # status
        self.status=QLabel("Ready"); root.addWidget(self.status)

        # debounce + fullscreen
        self.debounce=QTimer(self); self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self._kick_preview_thread)
        self.setStyleSheet("""
            QWidget{ font-size:12px; color:#222; }
            QGroupBox{ border:1px solid #e6e9ee; border-radius:10px; padding:8px 10px 6px 10px; background:#ffffff; margin-top:8px; }
            QGroupBox::title{ subcontrol-origin: margin; left:10px; padding:0 4px; color:#4a5568; font-weight:600; }
            QPushButton{ background:#ffffff; border:1px solid #d0d5db; border-radius:8px; padding:6px 10px; }
            QPushButton:hover{ background:#f1f5f9; }
            QLabel{ background:transparent; }
        """)
        self.showMaximized()

    # ------- groups -------
    def group_basic(self):
        g=QGroupBox("Basic"); f=QFormLayout(g)
        s,l=add_slider(f, QLabel("Exposure"),"exposure",-3,3,DEFAULTS["exposure"],0.01,self.on_change,self.on_reset_one); self.sliders["exposure"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Contrast"),"contrast",-1,1,DEFAULTS["contrast"],0.01,self.on_change,self.on_reset_one); self.sliders["contrast"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Gamma"),"gamma",0.3,2.2,DEFAULTS["gamma"],0.01,self.on_change,self.on_reset_one); self.sliders["gamma"]={"s":s,"l":l,"step":0.01}
        return g
    def group_tone(self):
        g=QGroupBox("Tone"); f=QFormLayout(g)
        for k,lab in [("highlights","Highlights"),("shadows","Shadows"),("whites","Whites"),("blacks","Blacks")]:
            s,l=add_slider(f, QLabel(lab), k, -1,1,DEFAULTS[k],0.01,self.on_change,self.on_reset_one); self.sliders[k]={"s":s,"l":l,"step":0.01}
        return g
    def group_color(self):
        g=QGroupBox("Color"); f=QFormLayout(g)
        for k,lab in [("saturation","Saturation"),("vibrance","Vibrance"),("temperature","Temperature"),("tint","Tint")]:
            s,l=add_slider(f, QLabel(lab), k, -1,1,DEFAULTS[k],0.01,self.on_change,self.on_reset_one); self.sliders[k]={"s":s,"l":l,"step":0.01}
        return g
    def group_effects(self):
        g=QGroupBox("Effects"); f=QFormLayout(g)
        s,l=add_slider(f, QLabel("Clarity"), "clarity", -1,1,DEFAULTS["clarity"],0.01,self.on_change,self.on_reset_one); self.sliders["clarity"]={"s":s,"l":l,"step":0.01}
        return g
    def group_hsl(self):
        w=QWidget(); outer=QVBoxLayout(w); outer.setContentsMargins(4,4,4,4); outer.setSpacing(10)
        g_h=QGroupBox("Color Mixer – Hue (°)"); f_h=QFormLayout(g_h)
        for c in _COLORS:
            key=f"h_{c}"
            chip=create_chip(_COLOR_SWATCH[c], _COLOR_LABEL[c]+" Hue")
            s,l=add_slider(f_h, chip, key, -60, 60, DEFAULTS[key], 1.0, self.on_change, self.on_reset_one, color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":1.0}
        outer.addWidget(g_h)
        g_s=QGroupBox("Color Mixer – Saturation"); f_s=QFormLayout(g_s)
        for c in _COLORS:
            key=f"s_{c}"
            chip=create_chip(_COLOR_SWATCH[c], _COLOR_LABEL[c]+" Saturation")
            s,l=add_slider(f_s, chip, key, -1.0, 1.0, DEFAULTS[key], 0.01, self.on_change, self.on_reset_one, color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":0.01}
        outer.addWidget(g_s)
        g_l=QGroupBox("Color Mixer – Luminance"); f_l=QFormLayout(g_l)
        for c in _COLORS:
            key=f"l_{c}"
            chip=create_chip(_COLOR_SWATCH[c], _COLOR_LABEL[c]+" Luminance")
            s,l=add_slider(f_l, chip, key, -1.0, 1.0, DEFAULTS[key], 0.01, self.on_change, self.on_reset_one, color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":0.01}
        outer.addWidget(g_l)
        return w

    # ------- persistence helpers -------
    def _persist_current_item(self):
        if self.current < 0:
            self.catalog["__ui__"] = {
                "preview_size": self.cmb_prev.currentText(),
                "sharpness": self.cmb_sharp.currentText()
            }
            save_catalog(self.catalog); return
        it = self.items[self.current]
        self.catalog[it["name"]] = {
            "settings": it["settings"],
            "star": bool(it.get("star", False))
        }
        self.catalog["__ui__"] = {
            "preview_size": self.cmb_prev.currentText(),
            "sharpness": self.cmb_sharp.currentText()
        }
        save_catalog(self.catalog)

    def _remember_ui(self):
        self.catalog["__ui__"] = {
            "preview_size": self.cmb_prev.currentText(),
            "sharpness": self.cmb_sharp.currentText()
        }
        save_catalog(self.catalog)

    # ------- split toggle -------
    def toggle_split(self):
        self.split_mode = not self.split_mode
        if hasattr(self, "btnBA"):
            self.btnBA.setChecked(self.split_mode)
        self._kick_preview_thread(force=True)

    # ------- events -------
    def on_change(self, key, value):
        if self.current<0: return
        self.items[self.current]["settings"][key]=float(value)
        self.debounce.start(160)
        self._persist_current_item()

    def on_reset_one(self, key):
        if self.current<0: return
        self.items[self.current]["settings"][key]=DEFAULTS[key]
        self.load_settings_to_ui()
        self.debounce.start(120)
        self._persist_current_item()

    # ------- file ops -------
    def open_files(self):
        filt="RAW/Images (*.cr2 *.cr3 *.nef *.arw *.dng *.raf *.rw2 *.orf *.srw *.jpg *.jpeg *.png *.tif *.tiff)"
        files,_=QFileDialog.getOpenFileNames(self,"Open Files","",filt)
        if not files: return
        self.items.clear(); self.film.clear(); self.current=-1
        self.to_load=len(files); self.loaded=0; self.update_status()
        for p in files:
            self.items.append({"name":p,"full":None,"thumb":None,"settings":DEFAULTS.copy(),"star":False})
            saved = self.catalog.get(p)
            if saved:
                if isinstance(saved.get("settings"), dict):
                    self.items[-1]["settings"] = {**DEFAULTS, **saved["settings"]}
                self.items[-1]["star"] = bool(saved.get("star", False))
            w=DecodeWorker(p, thumb_w=72, thumb_h=48)
            w.signals.done.connect(self._on_decoded)
            w.signals.error.connect(lambda m: QMessageBox.warning(self,"Error",m))
            self.pool.start(w)

    def _on_decoded(self, item):
        idx=next((i for i,v in enumerate(self.items) if v["name"]==item["name"]),-1)
        if idx>=0:
            self.items[idx]["full"]=item["full"]; self.items[idx]["thumb"]=item["thumb"]
            pix=QPixmap.fromImage(QImage(item["thumb"].data, item["thumb"].shape[1], item["thumb"].shape[0], 3*item["thumb"].shape[1], QImage.Format_RGB888))
            pix=badge_star(pix, self.items[idx].get("star",False))
            if self._pass_filter(self.items[idx]): filmstrip_add_item(self.film, pix, userdata=item["name"])
            if self.current<0 and self.film.count()>0: self.film.setCurrentRow(0)
            self.loaded+=1; self.update_status()

    def update_status(self, extra=""):
        if self.to_load>0 and self.loaded<self.to_load: self.status.setText(f"Loading... {self.loaded}/{self.to_load} {extra}")
        else: self.status.setText(extra if extra else "Ready")

    # ------- selection / star / filter / delete -------
    def on_select_item(self):
        rows=self.film.selectedIndexes()
        if not rows: return
        row=rows[0].row(); name=self.film.item(row).data(Qt.UserRole)
        self.current=next((i for i,v in enumerate(self.items) if v["name"]==name),-1)
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)

    def toggle_star_selected(self):
        rows=self.film.selectedIndexes()
        if not rows: return
        names=[self.film.item(r.row()).data(Qt.UserRole) for r in rows]
        for it in self.items:
            if it["name"] in names: it["star"]=not it.get("star",False)
        self.rebuild_filmstrip()
        if self.current >= 0:
            self._persist_current_item()
        else:
            self._remember_ui()

    def apply_filter(self, text):
        self.view_filter=text; self.rebuild_filmstrip()

    def _pass_filter(self, it)->bool:
        return True if self.view_filter=="All" else bool(it.get("star",False))

    def rebuild_filmstrip(self):
        selected=[self.film.item(i.row()).data(Qt.UserRole) for i in self.film.selectedIndexes()]
        self.film.blockSignals(True); self.film.clear()
        for it in self.items:
            if it["thumb"] is None or not self._pass_filter(it): continue
            pix=QPixmap.fromImage(QImage(it["thumb"].data, it["thumb"].shape[1], it["thumb"].shape[0], 3*it["thumb"].shape[1], QImage.Format_RGB888))
            pix=badge_star(pix, it.get("star",False)); filmstrip_add_item(self.film, pix, userdata=it["name"])
        for i in range(self.film.count()):
            if self.film.item(i).data(Qt.UserRole) in selected: self.film.item(i).setSelected(True)
        self.film.blockSignals(False)
        if self.current>=0 and not self._pass_filter(self.items[self.current]):
            if self.film.count()>0: self.film.setCurrentRow(0)
            else: self.current=-1; self.preview.setPixmap(QPixmap())
        self._kick_preview_thread(force=True)

    def delete_selected(self):
        rows=self.film.selectedIndexes()
        if not rows: QMessageBox.information(self,"Info","No selection"); return
        names={self.film.item(r.row()).data(Qt.UserRole) for r in rows}
        self.items=[it for it in self.items if it["name"] not in names]
        for name in list(self.catalog.keys()):
            if name in names:
                self.catalog.pop(name, None)
        save_catalog(self.catalog)
        self.rebuild_filmstrip()
        if self.film.count()>0: self.film.setCurrentRow(0)
        else: self.current=-1; self.preview.setPixmap(QPixmap())
        self.update_status("Removed selected")

    # ------- UI sync + threaded preview -------
    def load_settings_to_ui(self):
        if self.current<0: return
        st=self.items[self.current]["settings"]
        for key,cfg in self.sliders.items():
            val=float(st.get(key, DEFAULTS[key])); step=cfg["step"]; s=cfg["s"]; l=cfg["l"]
            s.blockSignals(True); s.setValue(int(val/step)); s.blockSignals(False); l.setText(f"{val:.2f}")

    def _kick_preview_thread(self, force=False):
        if self.current<0: return
        it=self.items[self.current]
        if it["full"] is None: return
        long_edge = int(self.cmb_prev.currentText())
        sharpen_amt = float(self.cmb_sharp.currentText())

        if self.split_mode:
            use_edge = max(320, long_edge // 2)  # ขนาดต่อ “ข้าง”
            mode = "split"
        else:
            use_edge = long_edge
            mode = "single"

        req_id = PreviewWorker.next_id()
        worker=PreviewWorker(it["full"], dict(it["settings"]), use_edge, sharpen_amt, mode, req_id)
        worker.signals.ready.connect(self._show_preview_pix)
        self.pool.start(worker)

    def _show_preview_pix(self, arr):
        h,w,_=arr.shape
        qimg=QImage(arr.data, w, h, 3*w, QImage.Format_RGB888)
        pix=QPixmap.fromImage(qimg).scaled(self.preview.width(), self.preview.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pix)

    def reset_current(self):
        if self.current<0: return
        self.items[self.current]["settings"]=DEFAULTS.copy()
        self.load_settings_to_ui(); self._kick_preview_thread(force=True)
        self.update_status("Reset photo")
        self._persist_current_item()

    # ------- Export -------
    def _ask_export_options(self):
        dlg=ExportOptionsDialog(self)
        if self.last_export_opts:
            o=self.last_export_opts
            dlg.cmb_fmt.setCurrentText(o.get("fmt","JPEG"))
            dlg.sp_quality.setValue(int(o.get("quality",92)))
            dlg.chk_prog.setChecked(bool(o.get("progressive",True)))
            dlg.chk_opt.setChecked(bool(o.get("optimize",True)))
            le=o.get("long_edge",None)
            if le is None: dlg.cmb_long.setCurrentText("No resize")
            elif le in (1200,1600,2048,3840): dlg.cmb_long.setCurrentText(str(le))
            else: dlg.cmb_long.setCurrentText("Custom"); dlg.sp_long.setValue(int(le)); dlg.sp_long.setEnabled(True)
            dlg.ed_suffix.setText(o.get("suffix","_edit"))
        return dlg.get_options() if dlg.exec()==QDialog.Accepted else None

    def _ask_outdir(self):
        d=QFileDialog.getExistingDirectory(self,"Choose Output Folder"); return d or ""

    def _start_export(self, items):
        if not items: QMessageBox.information(self,"Info","No images to export"); return
        opts=self._ask_export_options()
        if not opts: return
        out_dir=self._ask_outdir()
        if not out_dir: return
        self.last_export_opts=opts
        self.expdlg=QProgressDialog("Exporting...","Cancel",0,len(items),self)
        self.expdlg.setWindowTitle("Export"); self.expdlg.setWindowModality(Qt.WindowModal)
        self.expdlg.setAutoReset(False); self.expdlg.setAutoClose(False); self.expdlg.show()
        w=ExportWorker(items,out_dir,opts)
        w.signals.progress.connect(self._on_export_progress)
        w.signals.done.connect(self._on_export_done)
        w.signals.error.connect(self._on_export_error)
        self.pool.start(w); self.update_status("Exporting ...")

    def _on_export_progress(self, done,total):
        if self.expdlg: self.expdlg.setMaximum(total); self.expdlg.setValue(done); self.expdlg.setLabelText(f"Exporting... {done}/{total}")

    def _on_export_done(self, out_dir):
        if self.expdlg: self.expdlg.setValue(self.expdlg.maximum()); self.expdlg.close(); self.expdlg=None
        self.update_status(f"Done → {out_dir}"); QMessageBox.information(self,"Done",f"Export finished → {out_dir}")

    def _on_export_error(self, e):
        if self.expdlg: self.expdlg.close(); self.expdlg=None
        self.update_status("Export error"); QMessageBox.warning(self,"Error",str(e))

    def export_selected(self):
        rows=self.film.selectedIndexes()
        if not rows: QMessageBox.information(self,"Info","Select images (Ctrl/Shift)"); return
        names=[self.film.item(r.row()).data(Qt.UserRole) for r in rows]
        subset=[it for it in self.items if it["name"] in names and it["full"] is not None]
        self._start_export(subset)

    def export_all(self):
        ready=[it for it in self.items if it["full"] is not None]
        self._start_export(ready)

    def export_filtered(self):
        ready=[it for it in self.items if it["full"] is not None and self._pass_filter(it)]
        self._start_export(ready)

    # ------- ensure save on close -------
    def closeEvent(self, event):
        try:
            self._persist_current_item()
        except Exception:
            pass
        return super().closeEvent(event)

if __name__=="__main__":
    app=QApplication(sys.argv)
    w=Main()
    sys.exit(app.exec())
