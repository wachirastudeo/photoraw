import os, sys
import numpy as np
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QThreadPool, QSize, QLocale
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QFormLayout, QMessageBox, QComboBox, QProgressDialog,
    QFrame, QTabWidget, QSlider, QToolButton
)
from PySide6.QtGui import QPixmap

from catalog import load_catalog, save_catalog
from imaging import DEFAULTS
from workers import DecodeWorker, PreviewWorker, ExportWorker
from ui_helpers import add_slider, create_chip, create_filmstrip, filmstrip_add_item, badge_star, qimage_from_u8
from export_dialog import ExportOptionsDialog
from cropper import CropDialog

_COLOR_SWATCH = {
    "red":"#e53935","orange":"#fb8c00","yellow":"#fdd835","green":"#43a047",
    "aqua":"#26c6da","blue":"#1e88e5","purple":"#8e24aa","magenta":"#d81b60"
}
_COLORS = ["red","orange","yellow","green","aqua","blue","purple","magenta"]

class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAW Mini — Split Before/After + Crop/Rotate/Flip")
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
        self.pool=QThreadPool.globalInstance()

        # state
        self.items=[]; self.current=-1; self.view_filter="All"
        self.split_mode = False
        self.sliders={}
        self.to_load=0; self.loaded=0
        self.expdlg=None; self.last_export_opts=None

        self.catalog = load_catalog()

        root=QVBoxLayout(self)

        # top bar 1 (ไฟล์/พรีวิว/ฟิลเตอร์)
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

        # จำค่า UI เมื่อเปลี่ยน + รีเฟรชพรีวิว
        self.cmb_prev.currentTextChanged.connect(lambda _ : (self._remember_ui(), self._kick_preview_thread(force=True)))
        self.cmb_sharp.currentTextChanged.connect(lambda _ : (self._remember_ui(), self._kick_preview_thread(force=True)))
        last_ui = self.catalog.get("__ui__", {"preview_size": "900", "sharpness": "0.30"})
        try:
            self.cmb_prev.setCurrentText(last_ui.get("preview_size","900"))
            self.cmb_sharp.setCurrentText(last_ui.get("sharpness","0.30"))
        except Exception:
            pass

        # top bar 2 (Export/BeforeAfter/Transform)
        bar2=QHBoxLayout()
        btnExportSel=QPushButton("Export Selected"); btnExportSel.clicked.connect(self.export_selected)
        btnExportAll=QPushButton("Export All"); btnExportAll.clicked.connect(self.export_all)
        btnExportFilt=QPushButton("Export (Filtered)"); btnExportFilt.clicked.connect(self.export_filtered)

        # เพิ่มปุ่ม Reset
        btnReset=QPushButton("Reset All Settings"); btnReset.clicked.connect(self.reset_all_settings)
        
        btnBA=QPushButton("Before/After (Split)"); btnBA.setCheckable(True)
        btnBA.clicked.connect(self.toggle_split)
        self.btnBA = btnBA

        # Transform tools
        btnRotL=QPushButton("Rotate ⟲"); btnRotL.clicked.connect(lambda: self.bump_rotate(-90))
        btnRotR=QPushButton("Rotate ⟳"); btnRotR.clicked.connect(lambda: self.bump_rotate(+90))
        btnFlip=QPushButton("Flip ↔");   btnFlip.clicked.connect(self.toggle_flip_h)
        btnCrop=QPushButton("Crop");     btnCrop.clicked.connect(self.do_crop_dialog)

        bar2.addWidget(btnExportSel); bar2.addWidget(btnExportAll); bar2.addWidget(btnExportFilt)
        bar2.addStretch(1)
        bar2.addWidget(btnReset)  # เพิ่มปุ่ม Reset
        bar2.addWidget(btnBA)
        bar2.addSpacing(12)
        bar2.addWidget(btnRotL); bar2.addWidget(btnRotR); bar2.addWidget(btnFlip); bar2.addWidget(btnCrop)
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
        from imaging import DEFAULTS
        for k,conf in [("exposure",(-3,3,0.01)),("contrast",(-1,1,0.01)),("gamma",(0.3,2.2,0.01))]:
            s,l=add_slider(f, QLabel(k.capitalize()),k,conf[0],conf[1],DEFAULTS[k],conf[2],self.on_change,self.on_reset_one); self.sliders[k]={"s":s,"l":l,"step":conf[2]}
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
        from ui_helpers import create_chip
        w=QWidget(); outer=QVBoxLayout(w); outer.setContentsMargins(4,4,4,4); outer.setSpacing(10)
        g_h=QGroupBox("Color Mixer – Hue (°)"); f_h=QFormLayout(g_h)
        for c in _COLORS:
            key=f"h_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Hue")
            s,l=add_slider(f_h, chip, key, -60, 60, DEFAULTS[key], 1.0, self.on_change, self.on_reset_one, color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":1.0}
        outer.addWidget(g_h)
        g_s=QGroupBox("Color Mixer – Saturation"); f_s=QFormLayout(g_s)
        for c in _COLORS:
            key=f"s_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Saturation")
            s,l=add_slider(f_s, chip, key, -1.0, 1.0, DEFAULTS[key], 0.01, self.on_change, self.on_reset_one, color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":0.01}
        outer.addWidget(g_s)
        g_l=QGroupBox("Color Mixer – Luminance"); f_l=QFormLayout(g_l)
        for c in _COLORS:
            key=f"l_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Luminance")
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

    # ------- transforms -------
    def bump_rotate(self, delta):
        if self.current<0: return
        st=self.items[self.current]["settings"]
        st["rotate"] = (int(st.get("rotate",0)) + delta) % 360
        self._persist_current_item()
        self._kick_preview_thread(force=True)

    def toggle_flip_h(self):
        if self.current<0: return
        st=self.items[self.current]["settings"]
        st["flip_h"] = not bool(st.get("flip_h", False))
        self._persist_current_item()
        self._kick_preview_thread(force=True)

    def reset_all_settings(self):
        if self.current < 0:
            QMessageBox.information(self, "Info", "No image selected")
            return
        it = self.items[self.current]
        # รีเซ็ตค่าเป็นค่าเริ่มต้น
        it["settings"] = DEFAULTS.copy()
        # ลบการตั้งค่าการแปลงภาพที่อาจมีอยู่
        for k in ("crop", "rotate", "flip_h"):
            it["settings"].pop(k, None)
        self._persist_current_item()
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)
        self.update_status("Reset all settings")

    def do_crop_dialog(self):
        if self.current<0: return
        it=self.items[self.current]
        if it["full"] is None: return

        # สร้างภาพพรีวิวสำหรับ Crop โดยเฉพาะ
        # ต้องเป็นภาพที่ "แต่งสีแล้ว" แต่ "ยังไม่ transform" (crop/rotate/flip)
        # เพื่อให้ผู้ใช้เห็นภาพที่ถูกต้องและ Crop บนภาพนั้นได้
        from imaging import pipeline
        from ui_helpers import qimage_from_u8

        long_edge = int(self.cmb_prev.currentText())
        
        # Resize base image
        from PIL import Image
        h,w,_ = it["full"].shape
        s = long_edge / float(max(h,w)) if max(h,w) > long_edge else 1.0
        nw,nh = int(w*s), int(h*s)
        base_img = np.array(Image.fromarray(it["full"]).resize((nw,nh), Image.BILINEAR), dtype=np.uint8)

        # Apply color pipeline, but not transforms
        after01 = pipeline(base_img.astype(np.float32)/255.0, it["settings"])
        after_u8 = (np.clip(after01,0,1)*255.0 + 0.5).astype(np.uint8)
        pix = QPixmap.fromImage(qimage_from_u8(after_u8))

        dlg = CropDialog(pix, self)
        if dlg.exec():
            crop_norm = dlg.get_normalized_crop()
            if crop_norm:
                it["settings"]["crop"] = crop_norm
                self._persist_current_item()
                self._kick_preview_thread(force=True)
        # หมายเหตุ: crop ที่เก็บเป็น normalized จะใช้กับไฟล์ต้นฉบับตอน export ด้วย

    # ------- change events -------
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
            pm = QPixmap.fromImage(qimage_from_u8(item["thumb"]))
            pm = badge_star(pm, self.items[idx].get("star",False))
            if self._pass_filter(self.items[idx]): filmstrip_add_item(self.film, pm, userdata=item["name"])
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
            pm = QPixmap.fromImage(qimage_from_u8(it["thumb"]))
            pm = badge_star(pm, it.get("star",False)); filmstrip_add_item(self.film, pm, userdata=it["name"])
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
        from ui_helpers import qimage_from_u8
        qimg = qimage_from_u8(arr)
        pm = QPixmap.fromImage(qimg).scaled(self.preview.width(), self.preview.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)

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
        return dlg.get_options() if dlg.exec()==dlg.Accepted else None

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
