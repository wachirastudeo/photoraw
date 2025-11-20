import os, sys, json
import numpy as np
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QThreadPool, QSize, QLocale
from PySide6.QtWidgets import ( # NOQA
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QFormLayout, QMessageBox, QComboBox, QProgressDialog,
    QFrame, QTabWidget, QSlider, QToolButton, QDialog, QListWidget, QCheckBox, QSizePolicy, QScrollArea,
    QMainWindow, QToolBar, QMenuBar, QMenu
) # NOQA
from PySide6.QtGui import QPixmap, QGuiApplication, QPalette, QColor, QPainter, QPainterPath, QAction

from catalog import load_catalog, save_catalog, DEFAULT_ROOT
from imaging import DEFAULTS
from PySide6.QtCore import QEvent, QPoint, QPointF
from workers import DecodeWorker, PreviewWorker, ExportWorker
from ui_helpers import add_slider, create_chip, create_filmstrip, filmstrip_add_item, badge_star, qimage_from_u8, FlowLayout, create_app_icon
from export_dialog import ExportOptionsDialog
from cropper import CropDialog
from PySide6.QtWidgets import QInputDialog, QListWidget, QDialogButtonBox

_COLOR_SWATCH = {
    "red":"#e53935","orange":"#fb8c00","yellow":"#fdd835","green":"#43a047",
    "aqua":"#26c6da","blue":"#1e88e5","purple":"#8e24aa","magenta":"#d81b60"
}
_COLORS = ["red","orange","yellow","green","aqua","blue","purple","magenta"]

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ninlab")
        
        # Load icon from file
        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            from PySide6.QtGui import QIcon
            app_icon = QIcon(str(icon_path))
            self.setWindowIcon(app_icon)
            QApplication.setWindowIcon(app_icon)
        
        self.resize(1400, 900)
        
        # --- [REVISED] Initialize Data Structures ---
        self._apply_app_theme()
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
        self.hsl_scroll = None; self.hsl_content = None
        self.preset_scroll = None; self.preset_content = None
        seeded = self._seed_default_presets()
        self.copied_settings = None  # สำหรับ copy/paste settings รายภาพ
        self.live_dragging = False
        self.live_inflight = False
        # Zoom/Pan state
        self.is_zoomed = False
        self.zoom_point_norm = QPointF(0.5, 0.5) # Normalized coords on full image
        self.pan_origin = None
        self._is_panning = False

        # Central Widget setup
        self.cw = QWidget()
        self.setCentralWidget(self.cw)
        root=QVBoxLayout(self.cw)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # --- Top Layout (Row 1: Project, File, View) ---
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        
        # Project Info
        self.lab_project = QLabel(self.project_dir.name)
        self.lab_project.setStyleSheet("font-weight:bold; color:#e0e7ff; padding:0 4px;")
        row1.addWidget(QLabel("Proj:"))
        row1.addWidget(self.lab_project)
        
        # File Actions
        btnNew = QPushButton("New"); btnNew.setToolTip("New Project"); btnNew.clicked.connect(self.new_project)
        btnSwitch = QPushButton("Switch"); btnSwitch.setToolTip("Switch Project"); btnSwitch.clicked.connect(self.switch_project)
        btnOpen = QPushButton("Open Images"); btnOpen.clicked.connect(self.open_files)
        btnNew.setFixedWidth(60); btnSwitch.setFixedWidth(80); btnOpen.setFixedWidth(100)
        row1.addWidget(btnNew); row1.addWidget(btnSwitch); row1.addWidget(btnOpen)
        
        # View Actions
        row1.addStretch(1) # Spacer
        
        self.btnZoomFit = QPushButton("Fit"); self.btnZoomFit.setCheckable(True); self.btnZoomFit.setChecked(True)
        self.btnZoomFit.clicked.connect(self.zoom_fit); self.btnZoomFit.setFixedWidth(50)
        
        self.btnZoom100 = QPushButton("100%"); self.btnZoom100.setCheckable(True)
        self.btnZoom100.clicked.connect(self.zoom_100); self.btnZoom100.setFixedWidth(60)
        
        self.btnSplit = QPushButton("Split View"); self.btnSplit.setCheckable(True)
        self.btnSplit.clicked.connect(self.toggle_split); self.btnSplit.setFixedWidth(80)
        
        row1.addWidget(self.btnZoomFit); row1.addWidget(self.btnZoom100); row1.addWidget(self.btnSplit)
        
        # Filter
        row1.addWidget(QLabel("  Filter:"))
        self.filterBox=QComboBox(); self.filterBox.addItems(["All","Starred"])
        self.filterBox.currentTextChanged.connect(self.apply_filter)
        row1.addWidget(self.filterBox)

        # Preview Size & Sharpness
        row1.addWidget(QLabel("  Size:"))
        self.cmb_prev = QComboBox(); self.cmb_prev.addItems(["540","720","900","1200"]); self.cmb_prev.setCurrentText("900")
        self.cmb_prev.setToolTip("Preview Size (px)")
        self.cmb_prev.currentTextChanged.connect(lambda _ : (self._remember_ui(), self._kick_preview_thread(force=True)))
        row1.addWidget(self.cmb_prev)
        
        row1.addWidget(QLabel("  Sharp:"))
        self.cmb_sharp = QComboBox(); self.cmb_sharp.addItems(["0.00","0.15","0.30","0.45","0.60","0.80","1.00"])
        self.cmb_sharp.setCurrentText("0.30")
        self.cmb_sharp.setToolTip("Preview Sharpness")
        self.cmb_sharp.currentTextChanged.connect(lambda _ : (self._remember_ui(), self._kick_preview_thread(force=True)))
        row1.addWidget(self.cmb_sharp)
        
        root.addLayout(row1)

        # --- Bottom Layout (Row 2: Edit, Tools, Export) ---
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        
        # Edit
        btnUndo = QPushButton("Undo"); btnUndo.clicked.connect(self.undo_last)
        btnRedo = QPushButton("Redo"); btnRedo.clicked.connect(self.redo_last)
        btnReset = QPushButton("Reset All"); btnReset.clicked.connect(self.reset_all_settings)
        row2.addWidget(btnUndo); row2.addWidget(btnRedo); row2.addWidget(btnReset)
        
        # Copy/Paste
        btnCopy = QPushButton("Copy"); btnCopy.setToolTip("Copy Settings"); btnCopy.clicked.connect(self.copy_settings)
        btnPaste = QPushButton("Paste"); btnPaste.setToolTip("Paste Settings"); btnPaste.clicked.connect(self.paste_settings)
        row2.addWidget(btnCopy); row2.addWidget(btnPaste)
        
        # Tools (Icons)
        btnRotL=QToolButton(); btnRotL.setText("⟲"); btnRotL.setToolTip("Rotate Left"); btnRotL.clicked.connect(lambda: self.bump_rotate(-90))
        btnRotR=QToolButton(); btnRotR.setText("⟳"); btnRotR.setToolTip("Rotate Right"); btnRotR.clicked.connect(lambda: self.bump_rotate(+90))
        btnFlip=QToolButton(); btnFlip.setText("↔"); btnFlip.setToolTip("Flip Horizontal"); btnFlip.clicked.connect(self.toggle_flip_h)
        btnCrop=QPushButton("Crop"); btnCrop.clicked.connect(self.do_crop_dialog)
        btnStar=QPushButton("★ Star"); btnStar.clicked.connect(self.toggle_star_selected)
        
        row2.addWidget(btnRotL); row2.addWidget(btnRotR); row2.addWidget(btnFlip); row2.addWidget(btnCrop)
        row2.addWidget(btnStar)
        
        row2.addStretch(1)
        
        # Export
        btnExpSel = QPushButton("Export Selected"); btnExpSel.clicked.connect(self.export_selected)
        btnExpAll = QPushButton("Export All"); btnExpAll.clicked.connect(self.export_all)
        row2.addWidget(btnExpSel); row2.addWidget(btnExpAll)
        
        root.addLayout(row2)

        # Remember UI settings
        # Remember UI settings
        self._apply_ui_from_catalog()

        # content
        content=QHBoxLayout()

        # preview
        self.preview=QLabel("Open files to start"); self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(500, 320)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setStyleSheet("QLabel{background:#09090b; color:#71717a; border:1px solid #3f3f46; border-radius:8px;}")
        self.preview.setMouseTracking(True) # สำคัญมากสำหรับ Pan/Zoom บน Mac
        content.addWidget(self.preview, 4)
        self.preview.installEventFilter(self)
        self._last_preview_qimg = None

        # right panel — Reset + Tabs (keep reset per-image visible near controls)
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(0,0,0,0); right_panel.setSpacing(0)

        self.tabs=QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet("") # Reset inline style to use global stylesheet
        self.tabs.addTab(self.group_basic(), "Basic")
        self.tabs.addTab(self.group_tone(), "Tone")
        self.tabs.addTab(self.group_color(), "Color")
        self.tabs.addTab(self.group_effects(), "Effects")
        self.tabs.addTab(self.group_hsl(), "HSL")
        self.tabs.addTab(self.group_presets_tab(), "Presets")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        right_panel.addWidget(self.tabs)

        right_wrap = QWidget(); right_wrap.setLayout(right_panel)
        right_wrap.setFixedWidth(410)  # keep tool panel wide enough for labels/buttons
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
        self.debounce.timeout.connect(self._debounced_actions)
        self.pan_update_timer = QTimer(self); self.pan_update_timer.setSingleShot(True)
        self.pan_update_timer.timeout.connect(self._refresh_zoom_preview)
        # Determine font based on platform to avoid "missing font family" warnings
        font_family = ".AppleSystemUIFont" if sys.platform == "darwin" else "Segoe UI"
        self.setStyleSheet(f"""
            QWidget{{ font-family: "{font_family}", Helvetica, Arial; font-size:12px; color:#f4f4f5; }}
            
            /* Toolbar */
            QToolBar {{ background:#27272a; border-bottom:1px solid #3f3f46; spacing:6px; padding:4px; }}
            QToolBar::separator {{ background:#3f3f46; width:1px; margin:4px 8px; }}
            
            /* MenuBar */
            QMenuBar {{ background:#18181b; border-bottom:1px solid #3f3f46; }}
            QMenuBar::item {{ background:transparent; padding:6px 10px; }}
            QMenuBar::item:selected {{ background:#3f3f46; border-radius:4px; }}
            QMenu {{ background:#27272a; border:1px solid #3f3f46; padding:4px; }}
            QMenu::item {{ padding:6px 24px 6px 12px; border-radius:4px; }}
            QMenu::item:selected {{ background:#4f46e5; color:white; }}
            QMenu::separator {{ height:1px; background:#3f3f46; margin:4px 0; }}
            
            /* GroupBox */
            QGroupBox{{ border:1px solid #3f3f46; border-radius:8px; padding:12px 10px 10px 10px; background:#27272a; margin-top:8px; }}
            QGroupBox::title{{ subcontrol-origin: margin; left:10px; padding:0 4px; color:#a1a1aa; font-weight:600; background:#27272a; }}
            
            /* Buttons */
            QPushButton, QToolButton {{ 
                background:#3f3f46; border:1px solid #52525b; border-radius:6px; padding:6px 12px; color:#f4f4f5; 
            }}
            QPushButton:hover, QToolButton:hover {{ background:#52525b; border-color:#71717a; }}
            QPushButton:pressed, QToolButton:pressed {{ background:#27272a; border-color:#52525b; }}
            QPushButton:checked, QToolButton:checked {{ background:#4f46e5; border-color:#4338ca; color:white; }}
            QToolButton {{ font-size: 16px; padding: 4px 8px; }}
            
            /* Sliders */
            QSlider::groove:horizontal {{ border:1px solid #3f3f46; height:4px; background:#18181b; margin:2px 0; border-radius:2px; }}
            QSlider::handle:horizontal {{ background:#818cf8; border:1px solid #6366f1; width:14px; height:14px; margin:-6px 0; border-radius:7px; }}
            QSlider::handle:horizontal:hover {{ background:#a5b4fc; }}
            QSlider::sub-page:horizontal {{ background:#6366f1; border-radius:2px; }}
            
            /* Tabs */
            QTabWidget::pane{{ border:1px solid #3f3f46; border-radius:8px; background:#27272a; top:-1px; }}
            QTabBar::tab{{ 
                padding:8px 16px; border:1px solid transparent; border-bottom:2px solid transparent; 
                background:transparent; color:#a1a1aa; font-weight:500;
            }}
            QTabBar::tab:selected{{ color:#f4f4f5; border-bottom:2px solid #6366f1; }}
            QTabBar::tab:hover{{ color:#e4e4e7; }}
            
            /* ComboBox */
            QComboBox {{ background:#3f3f46; border:1px solid #52525b; border-radius:6px; padding:4px 8px; color:#f4f4f5; }}
            QComboBox::drop-down {{ border:0px; }}
            QComboBox QAbstractItemView {{ background:#27272a; border:1px solid #52525b; selection-background-color:#4f46e5; color:#f4f4f5; }}
            
            /* ScrollArea */
            QScrollArea {{ border:0px; background:transparent; }}
            QScrollBar:vertical {{ border:0px; background:#18181b; width:10px; margin:0; }}
            QScrollBar::handle:vertical {{ background:#52525b; min-height:20px; border-radius:5px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
            
            QLabel{{ background:transparent; }}
            QDialog {{ background:#18181b; }}
        """)
        if seeded:
            self._refresh_preset_list()
        self.showMaximized()

    # ------- groups -------
    def group_basic(self):
        g=QGroupBox("Basic"); f=QFormLayout(g)
        from imaging import DEFAULTS
        for k,conf in [("exposure",(-3,3,0.01)),("contrast",(-1,1,0.01)),("gamma",(0.3,2.2,0.01))]:
            s,l=add_slider(f, QLabel(k.capitalize()),k,conf[0],conf[1],DEFAULTS[k],conf[2],
                            on_change=self.on_change,on_reset=self.on_reset_one,
                            on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end)
            self.sliders[k]={"s":s,"l":l,"step":conf[2]}
        btn = QPushButton("Reset Basic")
        btn.clicked.connect(lambda: self.reset_tab_settings(["exposure", "contrast", "gamma"]))
        f.addRow(btn)
        return g

    def group_presets_tab(self):
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        base = QVBoxLayout(container); base.setContentsMargins(8,8,8,8); base.setSpacing(10)

        # scrollable area for list
        content=QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer=QVBoxLayout(content); outer.setContentsMargins(0,0,0,0); outer.setSpacing(10); outer.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        self.lst_presets = QListWidget(); self.lst_presets.itemClicked.connect(self._apply_preset_by_item)
        self.lst_presets.setSelectionRectVisible(False)
        self.lst_presets.setFrameShape(QFrame.NoFrame)
        self.lst_presets.setFocusPolicy(Qt.NoFocus)
        self.lst_presets.setStyleSheet("""
            QListWidget{ border:0px; background:transparent; padding:4px; }
            QListWidget::item{ padding:8px 10px; margin:2px 0px; border:0px; color:#a1a1aa; border-radius:6px; }
            QListWidget::item:selected{ background:#4f46e5; color:white; }
            QListWidget::item:hover:!selected{ background:#3f3f46; color:#e4e4e7; }
        """)
        outer.addWidget(self.lst_presets)

        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preset_content = content
        self.preset_scroll = scroll

        # bottom action bar (sticky)
        action_wrap = QFrame(); action_wrap.setObjectName("presetActions")
        action_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        action_layout = QVBoxLayout(action_wrap); action_layout.setContentsMargins(0,8,0,0); action_layout.setSpacing(6)
        self.lab_active_preset = QLabel("Active preset: None")
        self.lab_active_preset.setStyleSheet("QLabel{padding:6px 8px; background:#312e81; border:1px solid #4338ca; border-radius:6px; color:#e0e7ff;}")
        self.chk_preset_transform = QCheckBox("Include crop/rotate/flip when applying")
        action_layout.addWidget(self.lab_active_preset)
        action_layout.addWidget(self.chk_preset_transform)
        btn_row1=QHBoxLayout(); btn_row1.setSpacing(6)
        btn_row2=QHBoxLayout(); btn_row2.setSpacing(6)
        btn_save=QPushButton("Save Current"); btn_save.clicked.connect(self.save_preset_dialog)
        btn_apply=QPushButton("Apply to Selected"); btn_apply.clicked.connect(self._apply_selected_preset)
        btn_all=QPushButton("Apply to All Loaded"); btn_all.clicked.connect(self.apply_preset_all)
        btn_filt=QPushButton("Apply to Filtered"); btn_filt.clicked.connect(self.apply_preset_filtered)
        # Removed old toolbar2 buttons as they are now in Menu/Toolbar
        # btnPaste=QPushButton("Paste Settings"); btnPaste.clicked.connect(self.paste_settings)
        # btnCopy=QPushButton("Copy Settings"); btnCopy.clicked.connect(self.copy_settings)
        # btnUndo=QPushButton("Undo"); btnUndo.clicked.connect(self.undo_last)
        # btnRedo=QPushButton("Redo"); btnRedo.clicked.connect(self.redo_last)
        # btnSavePreset=QPushButton("Save Preset"); btnSavePreset.clicked.connect(self.save_preset_dialog)
        # btnApplyPreset=QPushButton("Apply Preset"); btnApplyPreset.clicked.connect(self._apply_selected_preset)
        # btnExportSel=QPushButton("Export Selected"); btnExportSel.clicked.connect(self.export_selected)
        # btnExportAll=QPushButton("Export All"); btnExportAll.clicked.connect(self.export_all)
        # btnExportFilt=QPushButton("Export Filtered"); btn_filt.clicked.connect(self.apply_preset_filtered) # This line was already present, just moved the comment
        btn_del=QPushButton("Delete"); btn_del.clicked.connect(self.delete_selected_preset)
        for btn in (btn_save, btn_apply, btn_all, btn_filt, btn_del):
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_row1.addWidget(btn_save); btn_row1.addWidget(btn_apply); btn_row1.addWidget(btn_del); btn_row1.addStretch(1)
        btn_row2.addWidget(btn_all); btn_row2.addWidget(btn_filt); btn_row2.addStretch(1)
        action_layout.addLayout(btn_row1)
        action_layout.addLayout(btn_row2)

        base.addWidget(scroll, 1)
        base.addWidget(action_wrap, 0)
        self.preset_action_wrap = action_wrap
        self._refresh_preset_list()
        return container

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
        btn = QPushButton("Reset Tone")
        btn.clicked.connect(lambda: self.reset_tab_settings(["highlights", "shadows", "whites", "blacks", "mid_contrast", "dehaze"]))
        f.addRow(btn)
        return g

    def group_color(self):
        g=QGroupBox("Color"); f=QFormLayout(g)
        for k,lab in [("saturation","Saturation"),("vibrance","Vibrance"),("temperature","Temperature"),("tint","Tint")]:
            s,l=add_slider(f, QLabel(lab), k, -1,1,DEFAULTS[k],0.01,
                           on_change=self.on_change,on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end)
            self.sliders[k]={"s":s,"l":l,"step":0.01}
        btn = QPushButton("Reset Color")
        btn.clicked.connect(lambda: self.reset_tab_settings(["saturation", "vibrance", "temperature", "tint"]))
        f.addRow(btn)
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
        btn = QPushButton("Reset Effects")
        btn.clicked.connect(lambda: self.reset_tab_settings(["clarity", "texture", "denoise", "vignette", "export_sharpen"]))
        f.addRow(btn)
        return g

    def group_hsl(self):
        from ui_helpers import create_chip
        content=QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer=QVBoxLayout(content); outer.setContentsMargins(0,0,0,0); outer.setSpacing(12); outer.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        g_h=QGroupBox("Color Mixer – Hue (°)")
        f_h=QFormLayout(g_h)
        f_h.setHorizontalSpacing(10); f_h.setVerticalSpacing(6)
        for c in _COLORS:
            key=f"h_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Hue")
            s,l=add_slider(f_h, chip, key, -60, 60, DEFAULTS[key], 1.0,
                           on_change=self.on_change, on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start, on_release=self._on_slider_drag_end,
                           color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":1.0}
        outer.addWidget(g_h)
        g_s=QGroupBox("Color Mixer – Saturation")
        f_s=QFormLayout(g_s)
        f_s.setHorizontalSpacing(10); f_s.setVerticalSpacing(6)
        for c in _COLORS:
            key=f"s_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Saturation")
            s,l=add_slider(f_s, chip, key, -1.0, 1.0, DEFAULTS[key], 0.01,
                           on_change=self.on_change, on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start, on_release=self._on_slider_drag_end,
                           color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":0.01}
        outer.addWidget(g_s)
        g_l=QGroupBox("Color Mixer – Luminance")
        f_l=QFormLayout(g_l)
        f_l.setHorizontalSpacing(10); f_l.setVerticalSpacing(6)
        for c in _COLORS:
            key=f"l_{c}"
            chip=create_chip(_COLOR_SWATCH[c], c.capitalize()+" Luminance")
            s,l=add_slider(f_l, chip, key, -1.0, 1.0, DEFAULTS[key], 0.01,
                           on_change=self.on_change, on_reset=self.on_reset_one,
                           on_press=self._on_slider_drag_start, on_release=self._on_slider_drag_end,
                           color_hex=_COLOR_SWATCH[c])
            self.sliders[key]={"s":s,"l":l,"step":0.01}
        outer.addWidget(g_l)
        
        btn = QPushButton("Reset HSL")
        # Generate all HSL keys
        hsl_keys = []
        for c in _COLORS:
            hsl_keys.extend([f"h_{c}", f"s_{c}", f"l_{c}"])
        btn.clicked.connect(lambda: self.reset_tab_settings(hsl_keys))
        outer.addWidget(btn)
        
        outer.addStretch(1)

        scroll = QScrollArea()
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.hsl_content = content # for old sync logic, might remove
        self.hsl_scroll = scroll
        return scroll

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


        


    def _apply_app_theme(self):
        # Use a flat Fusion style on macOS to avoid Aqua spacing/truncation issues
        app = QApplication.instance()
        if sys.platform == "darwin":
            app.setStyle("Fusion")

        pal = QPalette()
        # Dark Theme Palette (Zinc-900 base)
        pal.setColor(QPalette.Window, QColor("#18181b"))
        pal.setColor(QPalette.WindowText, QColor("#f4f4f5"))
        pal.setColor(QPalette.Base, QColor("#27272a"))
        pal.setColor(QPalette.AlternateBase, QColor("#3f3f46"))
        pal.setColor(QPalette.Text, QColor("#f4f4f5"))
        pal.setColor(QPalette.Button, QColor("#27272a"))
        pal.setColor(QPalette.ButtonText, QColor("#f4f4f5"))
        pal.setColor(QPalette.Highlight, QColor("#6366f1")) # Indigo-500
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        pal.setColor(QPalette.Link, QColor("#818cf8"))
        app.setPalette(pal)

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
        it["applied_preset"] = None
        # ลบการตั้งค่าการแปลงภาพที่อาจมีอยู่
        for k in ("crop", "rotate", "flip_h"):
            it["settings"].pop(k, None)
        self._persist_current_item()
        self.load_settings_to_ui()
        self._kick_preview_thread(force=True)
        self.update_status("Reset all settings")
        self._mark_active_preset(None)

    def reset_tab_settings(self, keys):
        if self.current < 0: return
        it = self.items[self.current]
        self._push_undo(it)
        self.redo_stack.get(it["name"], []).clear()
        
        changed = False
        for k in keys:
            if k in it["settings"] and it["settings"][k] != DEFAULTS[k]:
                it["settings"][k] = DEFAULTS[k]
                changed = True
        
        if changed:
            self._persist_current_item()
            self.load_settings_to_ui()
            self._kick_preview_thread(force=True)
            self.update_status("Reset tab settings")

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

    def _debounced_actions(self):
        self._kick_preview_thread()
        self._persist_current_item()

    def on_reset_one(self, key):
        if self.current<0: return
        it=self.items[self.current]
        self._push_undo(it)
        self.redo_stack.get(it["name"], []).clear()
        it["settings"][key]=DEFAULTS[key]
        self.load_settings_to_ui()
        self.debounce.start(100)
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
        
        # Check for toggle-off (if clicking the already active preset)
        preset_name = item.text()
        if self.current >= 0:
            it = self.items[self.current]
            if it.get("applied_preset") == preset_name:
                # Toggle OFF: Reset to defaults but preserve transforms
                self._push_undo(it)
                from imaging import DEFAULTS
                # Keep crop, rotate, flip_h
                transforms = {k: it["settings"][k] for k in ("crop", "rotate", "flip_h") if k in it["settings"]}
                it["settings"] = DEFAULTS.copy()
                it["settings"].update(transforms)
                it["applied_preset"] = None
                
                self._persist_current_item()
                self.load_settings_to_ui()
                self._kick_preview_thread(force=True)
                self.update_status(f"Removed preset '{preset_name}'")
                self._mark_active_preset(None)
                self.lst_presets.clearSelection()
                return

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

    def _push_undo(self, it, clear_redo=True):
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
        if clear_redo:
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
        # push current to undo, but DO NOT clear redo stack because we are consuming it
        self._push_undo(it, clear_redo=False)
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
            use_edge = min(use_edge, 720) # Use a smaller preview for live dragging

        base_override = None
        # Zooming is dynamic, don't use cache for it.
        cache = it.setdefault("preview_cache", {}) if not self.is_zoomed else {}
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
        worker=PreviewWorker(it["full"], dict(it["settings"]), use_edge, sharpen_amt, mode, req_id,
                             live=self.live_dragging, base_override=base_override,
                             is_zoomed=self.is_zoomed, zoom_point=self.zoom_point_norm,
                             preview_size=self.preview.size())
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

    # ------- Zoom Tools -------
    def zoom_fit(self):
        self.is_zoomed = False
        self.pan_update_timer.stop()
        self._update_zoom_buttons()
        self._kick_preview_thread(force=True)

    def zoom_100(self):
        self.is_zoomed = True
        self.pan_update_timer.stop()
        self._update_zoom_buttons()
        self._kick_preview_thread(force=True)

    def _update_zoom_buttons(self):
        self.btnZoomFit.setChecked(not self.is_zoomed)
        self.btnZoom100.setChecked(self.is_zoomed)

    def _reset_zoom(self):
        self.is_zoomed = False
        self.zoom_point_norm = QPointF(0.5, 0.5)
        self.pan_update_timer.stop()

    def _refresh_zoom_preview(self):
        self._kick_preview_thread(force=True)

    def _schedule_pan_preview_update(self):
        # restart timer so continuous drags coalesce into ~60fps updates
        self.pan_update_timer.start(16)

    def _show_preview_pix(self, arr):
        from ui_helpers import qimage_from_u8
        qimg = qimage_from_u8(arr)
        self._last_preview_qimg = qimg

        pm = QPixmap.fromImage(qimg).scaled(self.preview.width(), self.preview.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.preview.setAlignment(Qt.AlignCenter) # Force re-alignment
        self.live_inflight = False

    def eventFilter(self, obj, event):
        # [REVISED] This logic is designed to be robust for both mouse and trackpad gestures on macOS.
        if obj is not self.preview or self.current < 0:
            return super().eventFilter(obj, event)

        # --- Mouse Press: Prepare for a pan or a click-to-zoom ---
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if self.is_zoomed:
                self.pan_origin = event.position().toPoint()
                self._is_panning = False # Reset panning flag, will be set on first move
            return True

        # --- Mouse Move: Handle the actual panning action ---
        elif event.type() == QEvent.MouseMove:
            # Condition: We are zoomed, left button is down, and a pan has been initiated.
            if self.is_zoomed and self.pan_origin is not None and (event.buttons() & Qt.LeftButton):
                self.preview.setCursor(Qt.ClosedHandCursor)
                self._is_panning = True
                delta = event.position().toPoint() - self.pan_origin
                self.pan_origin = event.position().toPoint()

                # Convert pixel delta to normalized delta
                scale_factor = 2.0  # Approximation for 100% zoom vs fit
                dx = delta.x() / (self.preview.width() * scale_factor)
                dy = delta.y() / (self.preview.height() * scale_factor)

                self.zoom_point_norm.setX(max(0.0, min(1.0, self.zoom_point_norm.x() - dx)))
                self.zoom_point_norm.setY(max(0.0, min(1.0, self.zoom_point_norm.y() - dy)))
                self._schedule_pan_preview_update()
            # If just hovering (not panning), update cursor
            elif self.is_zoomed:
                self.preview.setCursor(Qt.OpenHandCursor)
            else:
                self.preview.setCursor(Qt.CrossCursor)
            return True # Consume mouse move events over the preview

        # --- Mouse Release: Finalize the action (pan or click) ---
        elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self.is_zoomed:
                # If no movement occurred, it was a click to zoom out.
                if not self._is_panning:
                    self.zoom_fit()
                self.preview.setCursor(Qt.OpenHandCursor)
                if self._is_panning and self.pan_update_timer.isActive():
                    self.pan_update_timer.stop()
                    self._kick_preview_thread(force=True)
            else:  # Was not zoomed, so this click means "zoom in"
                self.is_zoomed = True
                pm_rect = self.preview.pixmap().rect()
                label_rect = self.preview.contentsRect()
                offset_x = (label_rect.width() - pm_rect.width()) // 2
                offset_y = (label_rect.height() - pm_rect.height()) // 2
                click_on_pixmap = event.position().toPoint() - QPoint(offset_x, offset_y)
                nx = click_on_pixmap.x() / pm_rect.width() if pm_rect.width() > 0 else 0.5
                ny = click_on_pixmap.y() / pm_rect.height() if pm_rect.height() > 0 else 0.5
                self.zoom_point_norm = QPointF(max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny)))
                self._update_zoom_buttons()
                self._kick_preview_thread(force=True)

            # Always reset panning state on release
            self.pan_origin = None
            self._is_panning = False
            return True

        # --- Mouse Leave: Clear cursor ---
        elif event.type() == QEvent.Leave:
            self.preview.unsetCursor()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        # Keep preview scaled to the current space to avoid overflowing on smaller screens
        if self._last_preview_qimg is not None:
            pm = QPixmap.fromImage(self._last_preview_qimg).scaled(
                self.preview.width(), self.preview.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.preview.setPixmap(pm)
        QTimer.singleShot(0, self._sync_scroll_tabs) # Defer tab sync to prevent layout instability
        super().resizeEvent(event)

    def _on_tab_changed(self, index):
        QTimer.singleShot(1, self._sync_scroll_tabs) # Delay sync to allow tab to become visible

    def showEvent(self, event):
        return super().showEvent(event)

    def _sync_scroll_tabs(self):
        # [REVISED] This function is critical for layout stability.
        # The old logic forced a minimum height, causing the window to overflow on smaller screens.
        # The new logic simply ensures the content inside the scroll area can expand horizontally
        # to fit the available width, without forcing any vertical size. This lets Qt's layout
        # engine correctly manage the window size based on screen dimensions.
        if not hasattr(self, "tabs") or self.tabs is None or self.tabs.width() < 100: return
        viewport_w = self.tabs.width() - 40 # Leave some margin for scrollbar and padding
        for scroll, content in ((self.hsl_scroll, self.hsl_content), (self.preset_scroll, self.preset_content)):
            if scroll and content and scroll.widget():
                content.setMinimumWidth(viewport_w)

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
        
        # New Presets
        "Cool Matte": base(saturation=-0.2, vibrance=-0.1, temperature=-0.1, blacks=0.1, mid_contrast=-0.1, vignette=0.15),
        "B&W High Contrast": base(saturation=-1.0, vibrance=-1.0, contrast=0.25, mid_contrast=0.15, clarity=0.15, highlights=0.1, shadows=-0.1, export_sharpen=0.5),
        "Vintage Warm": base(temperature=0.15, tint=0.05, contrast=-0.1, gamma=1.05, blacks=0.1, vignette=0.25, texture=-0.05),
        "Cinematic": base(
            contrast=0.1, mid_contrast=0.05, vibrance=0.1, saturation=-0.1,
            # Teal shadows / Orange highlights approximation using HSL
            h_orange=-5, s_orange=0.1, l_orange=0.05,  # Skin tones
            h_blue=-10, s_blue=0.2, l_blue=-0.1,       # Shadows/Blues -> Teal
            h_aqua=10, s_aqua=0.1,                     # Aqua -> Teal
            vignette=0.15, export_sharpen=0.3
        ),
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
        self.project_dir = proj_dir.resolve()
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = load_catalog(self.project_dir)
        self.presets = self.catalog.get("__presets__", {})
        self.active_preset = None
        self.undo_stack.clear(); self.redo_stack.clear()
        self.items.clear(); self.current=-1; self.view_filter="All"; self.split_mode=False
        if hasattr(self, "film"): self.film.clear()
        if hasattr(self, "preview"): self.preview.setPixmap(QPixmap())
        self.lab_project.setText(self.project_dir.name)
        self._apply_ui_from_catalog()
        self._seed_default_presets()
        self._refresh_preset_list()
        self._save_last_project()

    def new_project(self):
        d = QFileDialog.getExistingDirectory(self,"Create / Choose Project Folder", str(DEFAULT_ROOT))
        if not d or not Path(d).is_dir(): return
        self._load_project(Path(d))

    def switch_project(self):
        d = QFileDialog.getExistingDirectory(self,"Switch Project", str(DEFAULT_ROOT))
        if not d or not Path(d).is_dir(): return
        self._load_project(Path(d))

if __name__=="__main__":
    # macOS HiDPI / Retina: rely on Qt6 auto scaling, just adjust rounding and layer usage
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    # if sys.platform == "darwin":
    #     os.environ.setdefault("QT_MAC_WANTS_LAYER", "1") # This can cause blank screens on some macOS/Qt versions
    app=QApplication(sys.argv)
    w=Main()
    sys.exit(app.exec())
