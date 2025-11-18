import os, sys, json
import numpy as np
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QThreadPool, QSize, QLocale
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QFormLayout, QMessageBox, QComboBox, QProgressDialog,
    QFrame, QTabWidget, QSlider, QToolButton, QDialog, QListWidget, QCheckBox
)
from PySide6.QtGui import QPixmap

from catalog import load_catalog, save_catalog, DEFAULT_ROOT
from imaging import DEFAULTS
from workers import DecodeWorker, PreviewWorker, ExportWorker
from ui_helpers import add_slider, create_chip, create_filmstrip, filmstrip_add_item, badge_star, qimage_from_u8
from export_dialog import ExportOptionsDialog
from cropper import CropDialog
from PySide6.QtWidgets import QInputDialog, QListWidget, QDialogButtonBox

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

        # project / catalog
        self.project_dir = self._load_last_project()
        self.catalog = load_catalog(self.project_dir)
        # state
        self.items=[]; self.current=-1; self.view_filter="All"
        self.split_mode = False
        self.sliders={}
        self.to_load=0; self.loaded=0
        self.expdlg=None; self.last_export_opts=None
        self._export_workers=[]
        self.presets = self.catalog.get("__presets__", {})  # name -> settings dict
        self.undo_stack = {}  # name -> list of settings snapshots (history)
        self.redo_stack = {}  # name -> redo history per image
        self.active_preset = None
        seeded = self._seed_default_presets()
        self.copied_settings = None  # สำหรับ copy/paste settings รายภาพ
        self.live_dragging = False
        self.live_inflight = False

        root=QVBoxLayout(self)

        # top bar 1 (ไฟล์/พรีวิว/ฟิลเตอร์)
        bar1=QHBoxLayout()
        btnOpen=QPushButton("Open"); btnOpen.clicked.connect(self.open_files)
        btnDelete=QPushButton("Delete Selected"); btnDelete.clicked.connect(self.delete_selected)
        btnStar=QPushButton("Toggle Star"); btnStar.clicked.connect(self.toggle_star_selected)
        self.filterBox=QComboBox(); self.filterBox.addItems(["All","Starred"]); self.filterBox.currentTextChanged.connect(self.apply_filter)
        btnProjNew=QPushButton("New Project"); btnProjNew.clicked.connect(self.new_project)
        btnProjOpen=QPushButton("Switch Project"); btnProjOpen.clicked.connect(self.switch_project)
        self.lab_project = QLabel(f"Project: {self.project_dir.name}")

        bar1.addWidget(btnOpen); bar1.addWidget(btnDelete); bar1.addWidget(btnStar)
        bar1.addStretch(1)
        bar1.addWidget(btnProjNew); bar1.addWidget(btnProjOpen); bar1.addWidget(self.lab_project)
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
        self._apply_ui_from_catalog()

        # top bar 2 (Export/BeforeAfter/Transform/Preset) single row
        bar2=QHBoxLayout()

        btnExportSel=QPushButton("Export Selected"); btnExportSel.clicked.connect(self.export_selected)
        btnExportAll=QPushButton("Export All"); btnExportAll.clicked.connect(self.export_all)
        btnExportFilt=QPushButton("Export (Filtered)"); btnExportFilt.clicked.connect(self.export_filtered)

        btnReset=QPushButton("Reset All Settings"); btnReset.clicked.connect(self.reset_all_settings)
        btnUndo=QPushButton("Undo"); btnUndo.clicked.connect(self.undo_last)
        btnRedo=QPushButton("Redo"); btnRedo.clicked.connect(self.redo_last)
        btnCopy=QPushButton("Copy Settings"); btnCopy.clicked.connect(self.copy_settings)
        btnPaste=QPushButton("Paste Settings"); btnPaste.clicked.connect(self.paste_settings)
        btnSavePreset=QPushButton("Save Preset"); btnSavePreset.clicked.connect(self.save_preset_dialog)
        btnApplyPreset=QPushButton("Apply Preset"); btnApplyPreset.clicked.connect(self.apply_preset_dialog)
        
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
        bar2.addWidget(btnUndo); bar2.addWidget(btnRedo)
        bar2.addWidget(btnCopy); bar2.addWidget(btnPaste); bar2.addWidget(btnReset)
        bar2.addWidget(btnSavePreset); bar2.addWidget(btnApplyPreset)
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

        # right panel — Reset + Tabs (keep reset per-image visible near controls)
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
        self.tabs.addTab(self.group_presets_tab(), "Presets")
        self.tabs.setFixedWidth(440)
        if seeded:
            self._refresh_preset_list()

        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(0,0,0,0); right_panel.setSpacing(8)
        btnResetImage = QPushButton("Reset This Image")
        btnResetImage.clicked.connect(self.reset_all_settings)
        right_panel.addWidget(btnResetImage)
        right_panel.addWidget(self.tabs, 1)
        right_panel.addStretch(1)
        right_wrap = QWidget(); right_wrap.setLayout(right_panel); right_wrap.setFixedWidth(440)
        content.addWidget(right_wrap, 0)
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
        container=QWidget(); outer=QVBoxLayout(container); outer.setContentsMargins(0,0,0,0); outer.setSpacing(8)

        g=QGroupBox("Basic"); f=QFormLayout(g)
        from imaging import DEFAULTS
        for k,conf in [("exposure",(-3,3,0.01)),("contrast",(-1,1,0.01)),("gamma",(0.3,2.2,0.01))]:
            s,l=add_slider(f, QLabel(k.capitalize()),k,conf[0],conf[1],DEFAULTS[k],conf[2],
                            on_change=self.on_change,on_reset=self.on_reset_one,
                            on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end)
            self.sliders[k]={"s":s,"l":l,"step":conf[2]}
        outer.addWidget(g)
        return container

    def group_presets_tab(self):
        w=QWidget(); outer=QVBoxLayout(w); outer.setContentsMargins(6,6,6,6); outer.setSpacing(8)
        self.lst_presets = QListWidget(); self.lst_presets.itemClicked.connect(self._apply_preset_by_item)
        self.lst_presets.setSelectionRectVisible(False)
        self.lst_presets.setFrameShape(QFrame.NoFrame)
        self.lst_presets.setFocusPolicy(Qt.NoFocus)
        self.lst_presets.setStyleSheet("""
            QListWidget{
                border:0px;
                background:transparent;
                padding:4px;
            }
            QListWidget::item{
                padding:8px 10px;
                margin:2px 0px;
                border:0px;
            }
            QListWidget::item:selected{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #2563eb, stop:1 #7c3aed);
                color:white;
                border-radius:8px;
                border:0px;
                outline:0;
            }
            QListWidget::item:selected:active{ outline:0; border:0px; }
            QListWidget::item:focus{ outline:0; }
            QListWidget::item:selected:!active{ background:#2563eb; color:white; }
        """)
        outer.addWidget(self.lst_presets, 1)
        self.lab_active_preset = QLabel("Active preset: None")
        self.lab_active_preset.setStyleSheet("QLabel{padding:6px 8px; background:#eef2ff; border:1px solid #c7d2fe; border-radius:6px; color:#1e3a8a;}")
        outer.addWidget(self.lab_active_preset)
        self.chk_preset_transform = QCheckBox("Include crop/rotate/flip when applying")
        outer.addWidget(self.chk_preset_transform)
        btn_row1=QHBoxLayout(); btn_row1.setSpacing(6)
        btn_row2=QHBoxLayout(); btn_row2.setSpacing(6)
        btn_save=QPushButton("Save Current"); btn_save.clicked.connect(self.save_preset_dialog)
        btn_apply=QPushButton("Apply to Selected"); btn_apply.clicked.connect(self._apply_selected_preset)
        btn_all=QPushButton("Apply to All Loaded"); btn_all.clicked.connect(self.apply_preset_all)
        btn_filt=QPushButton("Apply to Filtered"); btn_filt.clicked.connect(self.apply_preset_filtered)
        btn_del=QPushButton("Delete"); btn_del.clicked.connect(self.delete_selected_preset)
        # spread buttons into two rows for compact layout
        btn_row1.addWidget(btn_save); btn_row1.addWidget(btn_apply); btn_row1.addWidget(btn_del); btn_row1.addStretch(1)
        btn_row2.addWidget(btn_all); btn_row2.addWidget(btn_filt); btn_row2.addStretch(1)
        outer.addLayout(btn_row1)
        outer.addLayout(btn_row2)
        self._refresh_preset_list()
        return w

    def group_tone(self):
        g=QGroupBox("Tone"); f=QFormLayout(g)
        for k,lab in [("highlights","Highlights"),("shadows","Shadows"),("whites","Whites"),("blacks","Blacks")]:
            s,l=add_slider(f, QLabel(lab), k, -1,1,DEFAULTS[k],0.01,
                           on_change=self.on_change,on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end)
            self.sliders[k]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Mid Contrast"), "mid_contrast", -1,1,DEFAULTS["mid_contrast"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["mid_contrast"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Dehaze"), "dehaze", -0.5,1.0,DEFAULTS["dehaze"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["dehaze"]={"s":s,"l":l,"step":0.01}
        return g

    def group_color(self):
        g=QGroupBox("Color"); f=QFormLayout(g)
        for k,lab in [("saturation","Saturation"),("vibrance","Vibrance"),("temperature","Temperature"),("tint","Tint")]:
            s,l=add_slider(f, QLabel(lab), k, -1,1,DEFAULTS[k],0.01,
                           on_change=self.on_change,on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end)
            self.sliders[k]={"s":s,"l":l,"step":0.01}
        return g

    def group_effects(self):
        g=QGroupBox("Effects"); f=QFormLayout(g)
        s,l=add_slider(f, QLabel("Clarity"), "clarity", -1,1,DEFAULTS["clarity"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["clarity"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Texture"), "texture", -1,1,DEFAULTS["texture"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["texture"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Denoise"), "denoise", 0,1,DEFAULTS["denoise"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["denoise"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Vignette"), "vignette", 0,1,DEFAULTS["vignette"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["vignette"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Export Sharpen"), "export_sharpen", 0,1,DEFAULTS["export_sharpen"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["export_sharpen"]={"s":s,"l":l,"step":0.01}
        return g

    def group_hsl(self):
        from ui_helpers import create_chip
        w=QWidget(); outer=QVBoxLayout(w); outer.setContentsMargins(4,4,4,4); outer.setSpacing(10)
        g_h=QGroupBox("Color Mixer – Hue (°)"); f_h=QFormLayout(g_h)
        for c in _COLORS:
            key=f"h_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Hue")
            s,l=add_slider(f_h, chip, key, -60, 60, DEFAULTS[key], 1.0,
                           on_change=self.on_change, on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start, on_release=self._on_slider_drag_end,
                           color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":1.0}
        outer.addWidget(g_h)
        g_s=QGroupBox("Color Mixer – Saturation"); f_s=QFormLayout(g_s)
        for c in _COLORS:
            key=f"s_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Saturation")
            s,l=add_slider(f_s, chip, key, -1.0, 1.0, DEFAULTS[key], 0.01,
                           on_change=self.on_change, on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start, on_release=self._on_slider_drag_end,
                           color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":0.01}
        outer.addWidget(g_s)
        g_l=QGroupBox("Color Mixer – Luminance"); f_l=QFormLayout(g_l)
        for c in _COLORS:
            key=f"l_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Luminance")
            s,l=add_slider(f_l, chip, key, -1.0, 1.0, DEFAULTS[key], 0.01,
                           on_change=self.on_change, on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start, on_release=self._on_slider_drag_end,
                           color_hex=_COLOR_SWATCH[c])
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
            save_catalog(self.catalog, self.project_dir); return
        it = self.items[self.current]
        self.catalog[it["name"]] = {
            "settings": it["settings"],
            "star": bool(it.get("star", False)),
            "preset": it.get("applied_preset")
        }
        self.catalog["__ui__"] = {
            "preview_size": self.cmb_prev.currentText(),
            "sharpness": self.cmb_sharp.currentText()
        }
        self.catalog["__presets__"] = self.presets
        save_catalog(self.catalog, self.project_dir)

    def _remember_ui(self):
        self.catalog["__ui__"] = {
            "preview_size": self.cmb_prev.currentText(),
            "sharpness": self.cmb_sharp.currentText()
        }
        self.catalog["__presets__"] = self.presets
        save_catalog(self.catalog, self.project_dir)

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
        self._push_undo(it)
        self.redo_stack.get(it["name"], []).clear()
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
        it = self.items[self.current]
        self._push_undo(it)
        self.redo_stack.get(it["name"], []).clear()
        it["settings"][key]=float(value)
        self.debounce.start(25 if self.live_dragging else 100)
        self._persist_current_item()

    def on_reset_one(self, key):
        if self.current<0: return
        it=self.items[self.current]
        self._push_undo(it)
        self.redo_stack.get(it["name"], []).clear()
        it["settings"][key]=DEFAULTS[key]
        self.load_settings_to_ui()
        self.debounce.start(90)
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
                if "preset" in saved:
                    self.items[-1]["applied_preset"] = saved.get("preset")
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
        # initialize undo stack for this item
        cur_it = self.items[self.current]
        self.undo_stack.setdefault(name, [dict(cur_it["settings"])])
        self.redo_stack.setdefault(name, [])
        self.load_settings_to_ui()
        self._mark_active_preset(cur_it.get("applied_preset"))
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

    # ------- Presets -------
    def save_preset_dialog(self):
        if self.current < 0:
            QMessageBox.information(self,"Info","Select an image to save its settings as a preset"); return
        name, ok = QInputDialog.getText(self,"Save Preset","Preset name:")
        if not ok or not name.strip(): return
        safe = name.strip()
        # copy settings without transforms (crop/rotate/flip) so preset focuses on look
        st = {k:v for k,v in self.items[self.current]["settings"].items() if k not in ("crop","rotate","flip_h")}
        self.presets[safe] = st
        self.catalog["__presets__"] = self.presets
        save_catalog(self.catalog, self.project_dir)
        self._refresh_preset_list()
        QMessageBox.information(self,"Saved",f"Preset '{safe}' saved.")

    def apply_preset_dialog(self):
        if not self.presets:
            QMessageBox.information(self,"Info","No presets saved yet"); return
        dlg = QDialog(self); dlg.setWindowTitle("Apply Preset")
        lay = QVBoxLayout(dlg)
        lst = QListWidget(); [lst.addItem(n) for n in sorted(self.presets.keys())]
        lay.addWidget(lst)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(btns)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        if dlg.exec()!=QDialog.DialogCode.Accepted: return
        item = lst.currentItem()
        if not item: return
        preset_name = item.text()
        preset = self.presets.get(preset_name)
        if not preset: return
        if self.current < 0:
            QMessageBox.information(self,"Info","Select an image to apply the preset"); return
        it = self.items[self.current]
        self._apply_preset(it, preset, preset_name=preset_name)
        self._persist_current_item()
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)
        self.update_status(f"Applied preset '{preset_name}'")

    def _apply_preset_by_item(self, item):
        if not item: return
        self._apply_selected_preset()

    def _apply_selected_preset(self):
        item = self.lst_presets.currentItem() if hasattr(self,"lst_presets") else None
        if not item:
            QMessageBox.information(self,"Info","Select a preset"); return
        preset_name=item.text(); preset=self.presets.get(preset_name)
        if not preset:
            QMessageBox.information(self,"Info","Preset not found"); return
        if self.current<0:
            QMessageBox.information(self,"Info","Select an image to apply the preset"); return
        it=self.items[self.current]
        self._apply_preset(it, preset, include_transform=self.chk_preset_transform.isChecked() if hasattr(self,"chk_preset_transform") else False, preset_name=preset_name)
        self._persist_current_item()
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)
        self.update_status(f"Applied preset '{preset_name}'")
        self._mark_active_preset(preset_name)
        it["applied_preset"] = preset_name

    def delete_selected_preset(self):
        item = self.lst_presets.currentItem() if hasattr(self,"lst_presets") else None
        if not item: return
        name=item.text()
        if name in self.presets:
            self.presets.pop(name, None)
            self.catalog["__presets__"] = self.presets
            save_catalog(self.catalog, self.project_dir)
            self._refresh_preset_list()

    def apply_preset_all(self):
        item = self.lst_presets.currentItem() if hasattr(self,"lst_presets") else None
        if not item: QMessageBox.information(self,"Info","Select a preset first"); return
        preset_name = item.text()
        preset = self.presets.get(preset_name)
        if not preset: return
        include_tf = self.chk_preset_transform.isChecked() if hasattr(self,"chk_preset_transform") else False
        targets=[it for it in self.items if it["full"] is not None]
        self._apply_preset_to_items(targets, preset, include_tf, preset_name)
        self.update_status(f"Applied preset '{preset_name}' to all")
        self._mark_active_preset(preset_name)

    def apply_preset_filtered(self):
        item = self.lst_presets.currentItem() if hasattr(self,"lst_presets") else None
        if not item: QMessageBox.information(self,"Info","Select a preset first"); return
        preset_name = item.text()
        preset = self.presets.get(preset_name)
        if not preset: return
        include_tf = self.chk_preset_transform.isChecked() if hasattr(self,"chk_preset_transform") else False
        targets=[it for it in self.items if it["full"] is not None and self._pass_filter(it)]
        self._apply_preset_to_items(targets, preset, include_tf, preset_name)
        self.update_status(f"Applied preset '{preset_name}' to filtered")
        self._mark_active_preset(preset_name)

    def _apply_preset_to_items(self, items, preset, include_transform, preset_name):
        for it in items:
            self._apply_preset(it, preset, include_transform=include_transform, preset_name=preset_name)
            it["applied_preset"] = preset_name
            self.catalog[it["name"]] = {
                "settings": it["settings"],
                "star": bool(it.get("star", False)),
                "preset": preset_name
            }
        save_catalog(self.catalog, self.project_dir)
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)

    def _mark_active_preset(self, name):
        self.active_preset = name
        if hasattr(self,"lab_active_preset"):
            if name:
                self.lab_active_preset.setText(f"Active preset: {name}")
            else:
                self.lab_active_preset.setText("Active preset: None")
        if hasattr(self,"lst_presets"):
            if name:
                matches=self.lst_presets.findItems(name, Qt.MatchExactly)
                if matches:
                    self.lst_presets.setCurrentItem(matches[0])
            else:
                self.lst_presets.clearSelection()

    def _apply_preset(self, it, preset, include_transform=False, preset_name=None):
        self._push_undo(it)
        self.redo_stack.get(it.get("name"), []).clear()
        transforms = {k:it["settings"].get(k) for k in ("crop","rotate","flip_h") if include_transform and k in it["settings"]}
        it["settings"] = {**DEFAULTS, **preset, **transforms}
        if preset_name:
            it["applied_preset"] = preset_name

    def _refresh_preset_list(self):
        if not hasattr(self,"lst_presets"): return
        self.lst_presets.clear()
        for name in sorted(self.presets.keys()):
            self.lst_presets.addItem(name)
        if self.active_preset:
            matches=self.lst_presets.findItems(self.active_preset, Qt.MatchExactly)
            if matches:
                self.lst_presets.setCurrentItem(matches[0])

    def _push_undo(self, it):
        name = it.get("name", None)
        if not name: return
        self.undo_stack.setdefault(name, [])
        stack = self.undo_stack[name]
        # avoid duplicates
        if stack and stack[-1] == it["settings"]:
            return
        stack.append(dict(it["settings"]))
        if len(stack) > 20:
            stack.pop(0)
        # reset redo when new action happens
        self.redo_stack.setdefault(name, [])
        self.redo_stack[name].clear()
        # active preset/applied preset no longer valid after manual tweak
        it["applied_preset"] = None
        self._mark_active_preset(None)

    def undo_last(self):
        if self.current<0: return
        it=self.items[self.current]; name=it["name"]
        stack=self.undo_stack.get(name, [])
        if not stack: return
        # push current to redo
        self.redo_stack.setdefault(name, [])
        self.redo_stack[name].append(dict(it["settings"]))
        prev = stack.pop()
        it["settings"] = {**DEFAULTS, **prev}
        self._persist_current_item()
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)
        self.update_status("Undo")

    def redo_last(self):
        if self.current<0: return
        it=self.items[self.current]; name=it["name"]
        rstack=self.redo_stack.get(name, [])
        if not rstack: return
        # push current to undo
        self._push_undo(it)
        next_state = rstack.pop()
        it["settings"] = {**DEFAULTS, **next_state}
        self._persist_current_item()
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)
        self.update_status("Redo")

    # ------- copy / paste settings -------
    def copy_settings(self):
        if self.current < 0:
            QMessageBox.information(self,"Info","Select an image to copy settings"); return
        it = self.items[self.current]
        self.copied_settings = dict(it["settings"])
        self.update_status("Settings copied")

    def paste_settings(self):
        if self.current < 0:
            QMessageBox.information(self,"Info","Select an image to paste settings"); return
        if not self.copied_settings:
            QMessageBox.information(self,"Info","No copied settings"); return
        it = self.items[self.current]
        self._push_undo(it)
        self.redo_stack.get(it["name"], []).clear()
        it["settings"] = {**DEFAULTS, **self.copied_settings}
        it["applied_preset"] = None
        self._persist_current_item()
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)
        self.update_status("Pasted settings")

    def delete_selected(self):
        rows=self.film.selectedIndexes()
        if not rows: QMessageBox.information(self,"Info","No selection"); return
        names={self.film.item(r.row()).data(Qt.UserRole) for r in rows}
        self.items=[it for it in self.items if it["name"] not in names]
        for name in list(self.catalog.keys()):
            if name in names:
                self.catalog.pop(name, None)
        save_catalog(self.catalog, self.project_dir)
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
        self._refresh_preset_list()

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
        if self.live_dragging:
            if self.live_inflight:
                return
            use_edge = min(use_edge, 900)

        base_override = None
        cache = it.setdefault("preview_cache", {})
        cache_key = (mode, use_edge)
        if cache_key in cache:
            base_override = cache[cache_key]
        else:
            from PIL import Image
            h,w,_ = it["full"].shape
            if max(h,w)>use_edge:
                s = use_edge/float(max(h,w))
                nw,nh = int(w*s), int(h*s)
                base_override = np.array(Image.fromarray(it["full"]).resize((nw,nh), Image.BILINEAR), dtype=np.uint8)
            else:
                base_override = it["full"]
            cache[cache_key] = base_override

        req_id = PreviewWorker.next_id()
        worker=PreviewWorker(it["full"], dict(it["settings"]), use_edge, sharpen_amt, mode, req_id, live=self.live_dragging, base_override=base_override)
        worker.signals.ready.connect(self._show_preview_pix)
        if self.live_dragging:
            self.live_inflight = True
        self.pool.start(worker)

    def _on_slider_drag_start(self):
        self.live_dragging = True
        self._kick_preview_thread(force=True)

    def _on_slider_drag_end(self):
        self.live_dragging = False
        self._kick_preview_thread(force=True)

    def _show_preview_pix(self, arr):
        from ui_helpers import qimage_from_u8
        qimg = qimage_from_u8(arr)
        pm = QPixmap.fromImage(qimg).scaled(self.preview.width(), self.preview.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.live_inflight = False

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
        return dlg.get_options() if dlg.exec()==QDialog.DialogCode.Accepted else None

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
        self._export_workers.append(w)  # keep ref so signals stay alive
        self.pool.start(w); self.update_status("Exporting ...")

    def _on_export_progress(self, done,total):
        if self.expdlg: self.expdlg.setMaximum(total); self.expdlg.setValue(done); self.expdlg.setLabelText(f"Exporting... {done}/{total}")

    def _on_export_done(self, out_dir):
        if self.expdlg: self.expdlg.setValue(self.expdlg.maximum()); self.expdlg.close(); self.expdlg=None
        self._export_workers.clear()
        self.update_status(f"Done → {out_dir}"); QMessageBox.information(self,"Done",f"Export finished → {out_dir}")

    def _on_export_error(self, e):
        if self.expdlg: self.expdlg.close(); self.expdlg=None
        self._export_workers.clear()
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

    # ------- project helpers -------
    def _load_last_project(self):
        cfg = DEFAULT_ROOT / "_meta.json"
        try:
            if cfg.exists():
                data=json.loads(cfg.read_text(encoding="utf-8"))
                p=data.get("last_project")
                if p: return Path(p)
        except Exception:
            pass
        return DEFAULT_ROOT / "default"

    def _save_last_project(self):
        try:
            cfg = DEFAULT_ROOT / "_meta.json"; cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(json.dumps({"last_project": str(self.project_dir)}), encoding="utf-8")
        except Exception:
            pass

    def _apply_ui_from_catalog(self):
        last_ui = self.catalog.get("__ui__", {"preview_size": "900", "sharpness": "0.30"})
        try:
            self.cmb_prev.setCurrentText(last_ui.get("preview_size","900"))
            self.cmb_sharp.setCurrentText(last_ui.get("sharpness","0.30"))
        except Exception:
            pass

    def _default_presets(self):
        base = lambda **k: {**{kk:vv for kk,vv in DEFAULTS.items() if kk not in ("crop","rotate","flip_h")}, **k}
        return {
            "Clean Boost": base(exposure=0.25, contrast=0.12, clarity=0.08, vibrance=0.12, export_sharpen=0.35),
            "Vivid Punch": base(contrast=0.2, saturation=0.18, vibrance=0.22, texture=0.1, mid_contrast=0.08, export_sharpen=0.4),
            "Soft Film": base(contrast=-0.08, clarity=-0.06, texture=-0.04, gamma=1.05, vignette=0.12, export_sharpen=0.25),
            "Mono Matte": base(saturation=-1.0, vibrance=-1.0, contrast=-0.05, mid_contrast=0.1, clarity=0.04, vignette=0.08, export_sharpen=0.3),
            "Warm Portrait": base(contrast=0.06, highlights=-0.05, shadows=0.08, temperature=0.1, tint=0.05, clarity=0.02, vibrance=0.08, denoise=0.1),
        }

    def _seed_default_presets(self):
        changed = False
        defaults = self._default_presets()
        for name, vals in defaults.items():
            if name not in self.presets:
                self.presets[name] = vals
                changed = True
        if changed:
            self.catalog["__presets__"] = self.presets
            save_catalog(self.catalog, self.project_dir)
        return changed

    def _load_project(self, proj_dir: Path):
        self.project_dir = proj_dir
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = load_catalog(self.project_dir)
        self.presets = self.catalog.get("__presets__", {})
        self.active_preset = None
        self.undo_stack.clear(); self.redo_stack.clear()
        self.items.clear(); self.current=-1; self.view_filter="All"; self.split_mode=False
        if hasattr(self, "film"): self.film.clear()
        if hasattr(self, "preview"): self.preview.setPixmap(QPixmap())
        self.lab_project.setText(f"Project: {self.project_dir.name}")
        self._apply_ui_from_catalog()
        self._seed_default_presets()
        self._refresh_preset_list()
        self._save_last_project()

    def new_project(self):
        d = QFileDialog.getExistingDirectory(self,"Create / Choose Project Folder", str(DEFAULT_ROOT))
        if not d: return
        self._load_project(Path(d))

    def switch_project(self):
        d = QFileDialog.getExistingDirectory(self,"Switch Project", str(DEFAULT_ROOT))
        if not d: return
        self._load_project(Path(d))

if __name__=="__main__":
    app=QApplication(sys.argv)
    w=Main()
    sys.exit(app.exec())
