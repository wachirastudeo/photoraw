import os, sys, json
import numpy as np
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QThreadPool, QSize, QLocale
from PySide6.QtWidgets import ( # NOQA
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QFormLayout, QMessageBox, QComboBox, QProgressDialog,
    QFrame, QTabWidget, QSlider, QToolButton, QDialog, QListWidget, QCheckBox, QSizePolicy, QScrollArea,
    QMainWindow, QToolBar, QMenuBar, QMenu, QListWidgetItem, QInputDialog, QDialogButtonBox
) # NOQA
from PySide6.QtGui import QPixmap, QGuiApplication, QPalette, QColor, QPainter, QPainterPath, QAction, QIcon, QKeySequence, QShortcut

from catalog import load_catalog, save_catalog, DEFAULT_ROOT, load_projects_meta, update_project_info
from imaging import DEFAULTS
from PySide6.QtCore import QEvent, QPoint, QPointF
from workers import DecodeWorker, PreviewWorker, ExportWorker
from ui_helpers import add_slider, create_chip, create_filmstrip, filmstrip_add_item, badge_star, qimage_from_u8, FlowLayout, create_app_icon
from export_dialog import ExportOptionsDialog
from cropper import CropDialog


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
        
        # --- Initialize Project BEFORE creating UI ---
        self._apply_app_theme()
        self.create_menus()
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
        self.pool=QThreadPool.globalInstance()

        # Load project data
        self.project_dir = self._load_last_project()
        self.project_display_name = self._get_project_display_name()
        self.catalog = load_catalog(self.project_dir)
        self.presets = self.catalog.get("__presets__", {})
        self._init_default_presets()
        
        self.undo_stack={}; self.redo_stack={}
        self.items=[]; self.current=-1; self.view_filter="All"; self.split_mode=False
        self._clipboard=None; self.active_preset=None; self.live_dragging=False; self.live_inflight=False
        self._export_workers=[]; self.expdlg=None; self.last_export_opts=None
        self.to_load=0; self.loaded=0
        self._last_preview_qimg = None
        self.hsl_scroll = None; self.hsl_content = None
        self.preset_scroll = None; self.preset_content = None
        self.sliders={}
        
        # Zoom/Pan state
        self.is_zoomed = False
        self.zoom_point_norm = QPointF(0.5, 0.5)
        self.pan_origin = None
        self._is_panning = False
        self.pan_update_timer = QTimer()
        self.pan_update_timer.setSingleShot(True)
        self.pan_update_timer.timeout.connect(lambda: self._kick_preview_thread(force=True))

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
        self.lab_project = QLabel(self.project_display_name)
        self.lab_project.setStyleSheet("font-weight:bold; color:#e0e7ff; padding:0 4px;")
        self.lab_project.setToolTip(str(self.project_dir))
        row1.addWidget(QLabel("Project:"))
        row1.addWidget(self.lab_project)
        
        # File Actions
        btnNew = QPushButton("New"); btnNew.setToolTip("New Project"); btnNew.clicked.connect(self.new_project)
        btnSwitch = QPushButton("Switch"); btnSwitch.setToolTip("Switch Project"); btnSwitch.clicked.connect(self.switch_project)
        btnImport = QPushButton("Import Images"); btnImport.clicked.connect(self.import_images)
        btnDelete = QPushButton("Delete"); btnDelete.clicked.connect(self.delete_selected)
        btnNew.setFixedWidth(60); btnSwitch.setFixedWidth(80); btnImport.setFixedWidth(120); btnDelete.setFixedWidth(80)
        row1.addWidget(btnNew); row1.addWidget(btnSwitch); row1.addWidget(btnImport); row1.addWidget(btnDelete)
        
        # Shortcuts
        from PySide6.QtGui import QKeySequence
        QShortcut(QKeySequence.Delete, self, self.delete_selected)
        QShortcut(QKeySequence(Qt.Key_Backspace), self, self.delete_selected)
        QShortcut(QKeySequence.Undo, self, self.undo_last)
        QShortcut(QKeySequence.Redo, self, self.redo_last)
        QShortcut(QKeySequence.Copy, self, self.copy_settings)
        QShortcut(QKeySequence.Paste, self, self.paste_settings)
        QShortcut(QKeySequence(Qt.Key_Left), self, lambda: self.select_next_item(-1))
        QShortcut(QKeySequence(Qt.Key_Right), self, lambda: self.select_next_item(1))
        
        # View Actions
        row1.addStretch(1) # Spacer
        
        self.btnZoomFit = QPushButton("Fit"); self.btnZoomFit.setCheckable(True); self.btnZoomFit.setChecked(True)
        self.btnZoomFit.clicked.connect(self.zoom_fit); self.btnZoomFit.setFixedWidth(50)
        
        self.btnZoom100 = QPushButton("100%"); self.btnZoom100.setCheckable(True)
        self.btnZoom100.clicked.connect(self.zoom_100); self.btnZoom100.setFixedWidth(60)
        
        self.btnSplit = QPushButton("Before/After"); self.btnSplit.setCheckable(True)
        self.btnSplit.clicked.connect(self.toggle_split); self.btnSplit.setFixedWidth(100)
        
        row1.addWidget(self.btnZoomFit); row1.addWidget(self.btnZoom100); row1.addWidget(self.btnSplit)
        
        # Filter
        row1.addWidget(QLabel("  Filter:"))
        self.filterBox=QComboBox(); self.filterBox.addItems(["All","Starred"])
        self.filterBox.currentTextChanged.connect(self.apply_filter)
        row1.addWidget(self.filterBox)

        # Preview Size & Sharpness
        row1.addWidget(QLabel("  Size:"))
        self.cmb_prev = QComboBox(); self.cmb_prev.addItems(["540","720","900","1200","1600","2048"]); self.cmb_prev.setCurrentText("1200")
        self.cmb_prev.setToolTip("Preview Size (px)")
        self.cmb_prev.currentTextChanged.connect(lambda _ : (self._remember_ui(), self._kick_preview_thread(force=True)))
        row1.addWidget(self.cmb_prev)
        
        row1.addWidget(QLabel("  Sharp:"))
        self.cmb_sharp = QComboBox(); self.cmb_sharp.addItems(["0.00","0.15","0.30","0.45","0.60","0.80","1.00"])
        self.cmb_sharp.setCurrentText("0.30")
        self.cmb_sharp.setToolTip("Preview Sharpness")
        self.cmb_sharp.currentTextChanged.connect(lambda _ : (self._remember_ui(), self._kick_preview_thread(force=True)))
        row1.addWidget(self.cmb_sharp)
        
        # Low Spec Mode
        self.chk_low_spec = QCheckBox("Low Spec")
        self.chk_low_spec.setToolTip("Optimize for slower machines (reduce threads, smaller preview)")
        self.chk_low_spec.toggled.connect(self.toggle_low_spec_mode)
        row1.addWidget(self.chk_low_spec)
        
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
        btnExpStar = QPushButton("Export Starred ★"); btnExpStar.clicked.connect(self.export_starred)
        btnExpAll = QPushButton("Export All"); btnExpAll.clicked.connect(self.export_all)
        row2.addWidget(btnExpSel); row2.addWidget(btnExpStar); row2.addWidget(btnExpAll)
        
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
        self.tabs.addTab(self.group_info(), "Info")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        right_panel.addWidget(self.tabs)

        right_wrap = QWidget(); right_wrap.setLayout(right_panel)
        right_wrap.setFixedWidth(500)  # wider tool panel for better visibility
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
        seeded = self._seed_default_presets()
        if seeded:
            self._refresh_preset_list()
        
        # Restore images from the loaded project
        self._restore_project_images()
        
        self.showMaximized()

    # ------- groups -------
    def group_info(self):
        g = QGroupBox("Image Info")
        f = QFormLayout(g)
        
        self.lbl_name = QLabel("-")
        self.lbl_size = QLabel("-")
        self.lbl_dim = QLabel("-")
        self.lbl_camera = QLabel("-")
        self.lbl_iso = QLabel("-")
        self.lbl_aperture = QLabel("-")
        self.lbl_shutter = QLabel("-")
        self.lbl_lens = QLabel("-")
        self.lbl_date = QLabel("-")
        
        f.addRow("Name:", self.lbl_name)
        f.addRow("Size:", self.lbl_size)
        f.addRow("Dimensions:", self.lbl_dim)
        f.addRow("Camera:", self.lbl_camera)
        f.addRow("Lens:", self.lbl_lens)
        f.addRow("ISO:", self.lbl_iso)
        f.addRow("Aperture:", self.lbl_aperture)
        f.addRow("Shutter:", self.lbl_shutter)
        f.addRow("Date:", self.lbl_date)
        
        scroll = QScrollArea()
        scroll.setWidget(g)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        
        return scroll

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
        from curve_widget import CurveWidget
        g = QGroupBox("Effects")
        # Use QVBoxLayout for the main container to stack Curve and Sliders vertically
        main_layout = QVBoxLayout(g)
        
        # 1. Tone Curve Section
        curve_container = QWidget()
        curve_layout = QVBoxLayout(curve_container)
        curve_layout.setContentsMargins(0, 0, 0, 0)
        curve_layout.addWidget(QLabel("<b>Tone Curve</b>"))
        
        self.curve_widget = CurveWidget()
        self.curve_widget.setMinimumSize(256, 256) # Ensure fixed size
        self.curve_widget.setMaximumSize(256, 256)
        self.curve_widget.curveChanged.connect(self._on_curve_changed)
        
        # Center the curve widget
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(self.curve_widget)
        h_layout.addStretch()
        curve_layout.addLayout(h_layout)
        
        main_layout.addWidget(curve_container)
        
        # Add spacing
        main_layout.addSpacing(20)
        
        # 2. Sliders Section (using QFormLayout for alignment)
        sliders_container = QWidget()
        f = QFormLayout(sliders_container)
        f.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(sliders_container)
        
        # Add sliders to the form layout 'f'
        
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
        
        # Defringe
        s,l=add_slider(f, QLabel("Defringe"), "defringe", 0,1,DEFAULTS["defringe"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["defringe"]={"s":s,"l":l,"step":0.01}
        
        # Film Grain
        f.addRow(QLabel(""))  # Spacer
        f.addRow(QLabel("<b>Film Grain</b>"))
        s,l=add_slider(f, QLabel("Amount"), "grain_amount", 0,1,DEFAULTS["grain_amount"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["grain_amount"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Size"), "grain_size", 0,1,DEFAULTS["grain_size"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["grain_size"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Roughness"), "grain_roughness", 0,1,DEFAULTS["grain_roughness"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["grain_roughness"]={"s":s,"l":l,"step":0.01}
        s,l=add_slider(f, QLabel("Export Sharpen"), "export_sharpen", 0,1,DEFAULTS["export_sharpen"],0.01,
                       on_change=self.on_change,on_reset=self.on_reset_one,
                       on_press=self._on_slider_drag_start,on_release=self._on_slider_drag_end); self.sliders["export_sharpen"]={"s":s,"l":l,"step":0.01}
        btn = QPushButton("Reset Effects")
        btn.clicked.connect(lambda: self.reset_tab_settings(["clarity", "texture", "denoise", "vignette", "defringe", "grain_amount", "grain_size", "grain_roughness", "export_sharpen"]))
        f.addRow(btn)
        
        # Wrap in ScrollArea
        scroll = QScrollArea()
        scroll.setWidget(g)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        
        return scroll

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

    def toggle_low_spec_mode(self, enabled):
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        
        if enabled:
            # Reduce threads to half or 1
            max_threads = max(1, cpu_count // 2)
            self.pool.setMaxThreadCount(max_threads)
            
            # Force smaller preview if currently too large
            current_size = int(self.cmb_prev.currentText())
            if current_size > 900:
                self.cmb_prev.setCurrentText("900")
            
            self.update_status(f"Low Spec Mode: ON (Threads={max_threads})")
        else:
            # Restore threads
            self.pool.setMaxThreadCount(cpu_count)
            self.update_status(f"Low Spec Mode: OFF (Threads={cpu_count})")
            
        self._remember_ui()
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
        
        # Reset curve widget
        if hasattr(self, 'curve_widget'):
            self.curve_widget.reset_curve()
        
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
            # Reset curve widget if resetting effects tab
            if "clarity" in keys and hasattr(self, 'curve_widget'):
                self.curve_widget.reset_curve()
            
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
    
    def _on_curve_changed(self, lut):
        """Handle curve widget changes"""
        if self.current < 0: return
        it = self.items[self.current]
        self._push_undo(it)
        self.redo_stack.get(it["name"], []).clear()
        it["settings"]["curve_lut"] = lut.tolist()
        self._persist_current_item()
        self._kick_preview_thread(force=True)

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
    def import_images(self):
        filt="RAW/Images (*.cr2 *.cr3 *.nef *.arw *.dng *.raf *.rw2 *.orf *.srw *.jpg *.jpeg *.png *.tif *.tiff)"
        files,_=QFileDialog.getOpenFileNames(self,"Import Images","",filt)
        if not files: return
        
        # Don't clear items, append instead
        # self.items.clear(); self.film.clear(); self.current=-1
        
        existing_names = {it["name"] for it in self.items}
        new_files = [f for f in files if f not in existing_names]
        
        if not new_files:
            QMessageBox.information(self, "Info", "All selected files are already imported.")
            return
            
        self.to_load += len(new_files)
        # self.loaded=0 # Don't reset loaded count, just increment
        self.update_status(f"Importing {len(new_files)} images...")
        
        for p in new_files:
            self.items.append({"name":p,"full":None,"thumb":None,"settings":DEFAULTS.copy(),"star":False})
            saved = self.catalog.get(p)
            if saved:
                if isinstance(saved.get("settings"), dict):
                    self.items[-1]["settings"] = {**DEFAULTS, **saved["settings"]}
                self.items[-1]["star"] = bool(saved.get("star", False))
                if "preset" in saved:
                    self.items[-1]["applied_preset"] = saved.get("preset")
            else:
                # Register new file in catalog
                self.catalog[p] = {
                    "settings": DEFAULTS.copy(),
                    "star": False,
                    "preset": None
                }
        
        # Save catalog immediately to persist the file list
        save_catalog(self.catalog, self.project_dir)
            
        # Start workers for NEW items only
        # We need to find the index of the new items
        start_idx = len(self.items) - len(new_files)
        for i in range(start_idx, len(self.items)):
            item = self.items[i]
            w=DecodeWorker(item["name"], thumb_w=72, thumb_h=48)
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
        if self.current == -1: return
        # initialize undo stack for this item
        cur_it = self.items[self.current]
        self.undo_stack.setdefault(name, [dict(cur_it["settings"])])
        self.redo_stack.setdefault(name, [])
        
        # Update Info Tab
        try:
            from imaging import get_image_metadata
            fpath = self.project_dir / "images" / name
            meta = get_image_metadata(str(fpath))
            self.lbl_name.setText(meta.get("Name", "-"))
            self.lbl_size.setText(meta.get("Size", "-"))
            self.lbl_dim.setText(meta.get("Dimensions", "-"))
            self.lbl_camera.setText(meta.get("Camera", "-"))
            self.lbl_iso.setText(meta.get("ISO", "-"))
            self.lbl_aperture.setText(meta.get("Aperture", "-"))
            self.lbl_shutter.setText(meta.get("Shutter", "-"))
            self.lbl_lens.setText(meta.get("Lens", "-"))
            self.lbl_date.setText(meta.get("Date", "-"))
        except Exception as e:
            print(f"Error updating info: {e}")
        
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
            if it.get("thumb_edited"):
                pm = it["thumb_edited"]
            else:
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
    def _init_default_presets(self):
        """Initialize default presets if they don't exist"""
        changed = False
        
        # Remove deprecated presets
        deprecated = ["Matrix", "Fuji"]
        for name in deprecated:
            if name in self.presets:
                del self.presets[name]
                changed = True
        
        # Portrait Preset - Soft skin, warm tones
        if "Portrait" not in self.presets:
            self.presets["Portrait"] = {
                "exposure": 0.1,
                "contrast": -0.05,
                "highlights": 0.15,
                "shadows": 0.25,
                "whites": 0.0,
                "blacks": 0.1,
                "saturation": -0.1,
                "vibrance": 0.15,
                "temperature": 0.15,  # Warm
                "tint": 0.05,
                "gamma": 1.0,
                "clarity": -0.25,  # Soft skin
                "texture": -0.15,
                "mid_contrast": 0.0,
                "dehaze": 0.0,
                "denoise": 0.3,  # Smooth skin
                "vignette": 0.15,
                "defringe": 0.0,
                "export_sharpen": 0.15,
                "tone_curve": 0.0,
                "grain_amount": 0.0,
                "grain_size": 0.5,
                "grain_roughness": 0.5,
            }
            changed = True
        
        # Film Preset - Classic film look (always update to latest version)
        self.presets["Film"] = {
                "exposure": 0.05,
                "contrast": 0.25,
                "highlights": -0.1,
                "shadows": 0.1,
                "whites": -0.05,
                "blacks": 0.15,  # Lifted blacks
                "saturation": -0.2,  # Desaturated
                "vibrance": 0.0,
                "temperature": 0.05,
                "tint": 0.1,  # Slight magenta shift
                "gamma": 1.0,
                "clarity": 0.15,
                "texture": 0.1,
                "mid_contrast": 0.2,
                "dehaze": 0.0,
                "denoise": 0.0,
                "vignette": 0.25,
                "defringe": 0.0,
                "export_sharpen": 0.2,
                "tone_curve": 0.0,
                "grain_amount": 0.0,  # No grain by default
                "grain_size": 0.15,  # Fine grain if enabled
                "grain_roughness": 0.5,
            }
        
        # Kodachrome - Vibrant, warm, high contrast
        self.presets["Kodachrome"] = {
            "exposure": 0.1,
            "contrast": 0.35,
            "highlights": -0.15,
            "shadows": 0.05,
            "whites": 0.1,
            "blacks": -0.1,
            "saturation": 0.3,  # Vibrant colors
            "vibrance": 0.2,
            "temperature": 0.2,  # Warm
            "tint": -0.05,
            "gamma": 1.0,
            "clarity": 0.2,
            "texture": 0.15,
            "mid_contrast": 0.15,
            "dehaze": 0.0,
            "denoise": 0.0,
            "vignette": 0.2,
            "defringe": 0.0,
            "export_sharpen": 0.25,
            "tone_curve": 0.0,
            "grain_amount": 0.0,
            "grain_size": 0.2,
            "grain_roughness": 0.6,
        }
        
        # Portra - Soft, pastel, skin-friendly
        self.presets["Portra"] = {
            "exposure": 0.15,
            "contrast": -0.1,
            "highlights": 0.2,
            "shadows": 0.3,
            "whites": 0.05,
            "blacks": 0.2,  # Lifted blacks
            "saturation": -0.15,  # Pastel
            "vibrance": 0.1,
            "temperature": 0.1,  # Slightly warm
            "tint": 0.05,
            "gamma": 1.0,
            "clarity": -0.15,  # Soft
            "texture": -0.1,
            "mid_contrast": -0.05,
            "dehaze": 0.0,
            "denoise": 0.2,
            "vignette": 0.1,
            "defringe": 0.0,
            "export_sharpen": 0.15,
            "tone_curve": 0.0,
            "grain_amount": 0.0,
            "grain_size": 0.25,
            "grain_roughness": 0.4,
        }
        
        # Cinematic - Cool tones, moody, teal & orange
        self.presets["Cinematic"] = {
            "exposure": -0.05,
            "contrast": 0.3,
            "highlights": -0.2,
            "shadows": 0.15,
            "whites": -0.1,
            "blacks": 0.25,  # Lifted blacks for mood
            "saturation": -0.1,
            "vibrance": 0.15,
            "temperature": -0.15,  # Cool/teal
            "tint": 0.0,
            "gamma": 1.0,
            "clarity": 0.1,
            "texture": 0.05,
            "mid_contrast": 0.25,
            "dehaze": 0.1,
            "denoise": 0.0,
            "vignette": 0.35,  # Strong vignette
            "defringe": 0.0,
            "export_sharpen": 0.2,
            "tone_curve": 0.0,
            "grain_amount": 0.0,
            "grain_size": 0.18,
            "grain_roughness": 0.65,
        }
        
        # Faded Forest - Muted green, moody, cinematic
        self.presets["Faded Forest"] = {
            "exposure": -0.15,  # Darker
            "contrast": 0.35,  # High contrast
            "highlights": -0.2,
            "shadows": 0.25,  # Lifted shadows
            "whites": -0.1,
            "blacks": 0.3,  # Lifted blacks (moody)
            "saturation": -0.35,  # Muted/desaturated
            "vibrance": -0.05,
            "temperature": -0.2,  # Cool
            "tint": -0.1,  # Slight green
            "gamma": 1.0,
            "clarity": 0.2,
            "texture": 0.15,
            "mid_contrast": 0.2,
            "dehaze": 0.15,
            "denoise": 0.0,
            "vignette": 0.3,
            "defringe": 0.0,
            "export_sharpen": 0.2,
            "tone_curve": 0.0,
            "grain_amount": 0.0,
            "grain_size": 0.15,
            "grain_roughness": 0.6,
        }
        
        # Faded B&W - Black & white with lifted blacks
        self.presets["Faded B&W"] = {
            "exposure": 0.05,
            "contrast": 0.15,
            "highlights": 0.0,
            "shadows": 0.15,
            "whites": 0.0,
            "blacks": 0.35,  # Lifted blacks (not pure black)
            "saturation": -1.0,  # Black & white
            "vibrance": 0.0,
            "temperature": 0.0,
            "tint": 0.0,
            "gamma": 1.0,
            "clarity": 0.1,
            "texture": 0.05,
            "mid_contrast": 0.1,
            "dehaze": 0.0,
            "denoise": 0.0,
            "vignette": 0.15,
            "defringe": 0.0,
            "export_sharpen": 0.2,
            "tone_curve": 0.0,
            "grain_amount": 0.0,
            "grain_size": 0.2,
            "grain_roughness": 0.5,
        }
        
        changed = True
        
        if changed:
            self.catalog["__presets__"] = self.presets
            save_catalog(self.catalog, self.project_dir)
    
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
            use_edge = min(use_edge, 1600) # Use a smaller preview for live dragging

        base_override = None
        cache = it.setdefault("preview_cache", {})
        cache_key = (mode, use_edge)
        
        # For zoom mode, we need a processed full-resolution image
        if self.is_zoomed:
            # Check if we have a cached processed full image
            settings_hash = str(sorted(it["settings"].items()))
            zoom_cache_key = ("zoom_processed", settings_hash, sharpen_amt)
            
            if zoom_cache_key not in cache or force:
                # Process the full image and cache it
                # This happens once per settings change
                pass  # Will be processed in worker
            
            base_override = None  # Let worker handle zoom processing
        else:
            # Normal mode: use resized base image
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
                             preview_size=self.preview.size(),
                             processed_cache=cache,
                             low_spec=self.chk_low_spec.isChecked() if hasattr(self, "chk_low_spec") else False)
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
        from ui_helpers import qimage_from_u8, badge_star
        qimg = qimage_from_u8(arr)
        self._last_preview_qimg = qimg

        base_pm = QPixmap.fromImage(qimg)
        pm = base_pm.scaled(self.preview.width(), self.preview.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.preview.setAlignment(Qt.AlignCenter) # Force re-alignment
        self.live_inflight = False

        # Update thumbnail
        if self.current >= 0:
            it = self.items[self.current]
            thumb_pm = base_pm.scaled(72, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            it["thumb_edited"] = thumb_pm
            
            name = it["name"]
            for i in range(self.film.count()):
                item = self.film.item(i)
                if item.data(Qt.UserRole) == name:
                    final_pm = badge_star(thumb_pm, it.get("star", False))
                    item.setIcon(QIcon(final_pm))
                    break

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
        dlg = self.expdlg
        if dlg:
            dlg.setMaximum(total)
            dlg.setValue(done)
            dlg.setLabelText(f"Exporting... {done}/{total}")

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
    
    def export_starred(self):
        starred=[it for it in self.items if it["full"] is not None and it.get("star", False)]
        if not starred:
            QMessageBox.information(self,"Info","No starred images to export")
            return
        self._start_export(starred)

    def closeEvent(self, event):
        try:
            self._persist_current_item()
        except Exception:
            pass
        return super().closeEvent(event)

    # ------- project helpers -------
    def _load_last_project(self):
        meta = load_projects_meta()
        last_proj = meta.get("last_project")
        if last_proj and Path(last_proj).exists():
            return Path(last_proj)
        # Default project
        default_proj = DEFAULT_ROOT / "default"
        default_proj.mkdir(parents=True, exist_ok=True)
        update_project_info(default_proj, "Default Project")
        return default_proj

    def _get_project_display_name(self):
        """Get the display name for the current project"""
        meta = load_projects_meta()
        proj_str = str(self.project_dir.resolve())
        projects = meta.get("projects", {})
        if proj_str in projects:
            return projects[proj_str].get("display_name", self.project_dir.name)
        return self.project_dir.name

    def _save_last_project(self):
        update_project_info(self.project_dir)

    def _apply_ui_from_catalog(self):
        last_ui = self.catalog.get("__ui__", {"preview_size": "1200", "sharpness": "0.30"})
        try:
            self.cmb_prev.setCurrentText(last_ui.get("preview_size","1200"))
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

    def _load_project(self, proj_dir: Path, display_name: str = None):
        self.project_dir = proj_dir.resolve()
        self.project_dir.mkdir(parents=True, exist_ok=True)
        
        # Update metadata
        if display_name:
            update_project_info(self.project_dir, display_name)
        else:
            update_project_info(self.project_dir)
        
        self.project_display_name = self._get_project_display_name()
        self.catalog = load_catalog(self.project_dir)
        self.presets = self.catalog.get("__presets__", {})
        self.active_preset = None
        self.undo_stack.clear(); self.redo_stack.clear()
        self.items.clear(); self.current=-1; self.view_filter="All"; self.split_mode=False
        if hasattr(self, "film"): self.film.clear()
        if hasattr(self, "preview"): self.preview.setPixmap(QPixmap())
        self.lab_project.setText(self.project_display_name)
        self.lab_project.setToolTip(str(self.project_dir))
        self.setWindowTitle(f"Ninlab - {self.project_display_name}")
        self._apply_ui_from_catalog()
        self._seed_default_presets()
        self._refresh_preset_list()
        
        # Restore images from catalog
        image_files = [k for k in self.catalog.keys() if not k.startswith("__")]
        existing_files = []
        for k in image_files:
            try:
                if Path(k).exists():
                    existing_files.append(k)
            except Exception:
                pass
        
        if existing_files:
            self.to_load = len(existing_files)
            self.loaded = 0
            self.update_status(f"Restoring {len(existing_files)} images...")
            
            for p in existing_files:
                item = {"name": p, "full": None, "thumb": None, "settings": DEFAULTS.copy(), "star": False}
                saved = self.catalog.get(p)
                if saved:
                    if isinstance(saved.get("settings"), dict):
                        item["settings"] = {**DEFAULTS, **saved["settings"]}
                    item["star"] = bool(saved.get("star", False))
                    if "preset" in saved:
                        item["applied_preset"] = saved.get("preset")
                
                self.items.append(item)
                
                w = DecodeWorker(p, thumb_w=72, thumb_h=48)
                w.signals.done.connect(self._on_decoded)
                w.signals.error.connect(lambda m: print(f"Error loading: {m}"))
                self.pool.start(w)

    def _restore_project_images(self):
        """Restore images from the current project's catalog"""
        image_files = [k for k in self.catalog.keys() if not k.startswith("__")]
        existing_files = []
        for k in image_files:
            try:
                if Path(k).exists():
                    existing_files.append(k)
            except Exception:
                pass
        
        if existing_files:
            self.to_load = len(existing_files)
            self.loaded = 0
            self.update_status(f"Restoring {len(existing_files)} images...")
            
            for p in existing_files:
                item = {"name": p, "full": None, "thumb": None, "settings": DEFAULTS.copy(), "star": False}
                saved = self.catalog.get(p)
                if saved:
                    if isinstance(saved.get("settings"), dict):
                        item["settings"] = {**DEFAULTS, **saved["settings"]}
                    item["star"] = bool(saved.get("star", False))
                    if "preset" in saved:
                        item["applied_preset"] = saved.get("preset")
                
                self.items.append(item)
                
                w = DecodeWorker(p, thumb_w=72, thumb_h=48)
                w.signals.done.connect(self._on_decoded)
                w.signals.error.connect(lambda m: print(f"Error loading: {m}"))
                self.pool.start(w)



    def create_menus(self):
        bar = self.menuBar()
        
        # File Menu
        file_menu = bar.addMenu("File")
        
        # New Project
        action_new = QAction("New Project...", self)
        action_new.setShortcut("Ctrl+N")
        action_new.triggered.connect(self.new_project)
        file_menu.addAction(action_new)
        
        # Switch Project
        action_switch = QAction("Switch Project...", self)
        action_switch.setShortcut("Ctrl+O")
        action_switch.triggered.connect(self.switch_project)
        file_menu.addAction(action_switch)
        
        file_menu.addSeparator()
        
        # Import Images
        action_import = QAction("Import Images...", self)
        action_import.setShortcut("Ctrl+I")
        action_import.triggered.connect(self.import_images)
        file_menu.addAction(action_import)
        
        file_menu.addSeparator()
        
        # Reveal in Explorer
        action_reveal = QAction("Reveal Project in Explorer", self)
        action_reveal.triggered.connect(lambda: os.startfile(self.project_dir) if sys.platform=="win32" else None)
        file_menu.addAction(action_reveal)
        
        file_menu.addSeparator()
        
        # Exit
        action_exit = QAction("Exit", self)
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)
        
        # Edit Menu
        edit_menu = bar.addMenu("Edit")
        
        action_undo = QAction("Undo", self)
        action_undo.setShortcut(QKeySequence.Undo)
        action_undo.triggered.connect(self.undo_last)
        edit_menu.addAction(action_undo)
        
        action_redo = QAction("Redo", self)
        action_redo.setShortcut(QKeySequence.Redo)
        action_redo.triggered.connect(self.redo_last)
        edit_menu.addAction(action_redo)
        
        edit_menu.addSeparator()
        
        action_copy = QAction("Copy Settings", self)
        action_copy.setShortcut(QKeySequence.Copy)
        action_copy.triggered.connect(self.copy_settings)
        edit_menu.addAction(action_copy)
        
        action_paste = QAction("Paste Settings", self)
        action_paste.setShortcut(QKeySequence.Paste)
        action_paste.triggered.connect(self.paste_settings)
        edit_menu.addAction(action_paste)
        
        # Export Menu
        export_menu = bar.addMenu("Export")
        
        action_export_selected = QAction("Export Selected", self)
        action_export_selected.triggered.connect(self.export_selected)
        export_menu.addAction(action_export_selected)
        
        action_export_starred = QAction("Export Starred ★", self)
        action_export_starred.triggered.connect(self.export_starred)
        export_menu.addAction(action_export_starred)
        
        export_menu.addSeparator()
        
        action_export_all = QAction("Export All", self)
        action_export_all.triggered.connect(self.export_all)
        export_menu.addAction(action_export_all)
        
        action_export_filtered = QAction("Export Filtered", self)
        action_export_filtered.triggered.connect(self.export_filtered)
        export_menu.addAction(action_export_filtered)


    def new_project(self):
        # Ask for project name
        name, ok = QInputDialog.getText(self, "New Project", "Enter project name:")
        if not ok or not name.strip():
            return
        
        # Create unique folder name
        from datetime import datetime
        folder_name = name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_path = DEFAULT_ROOT / f"{folder_name}_{timestamp}"
        
        self._load_project(proj_path, name.strip())
        QMessageBox.information(self, "Success", f"Created project '{name.strip()}'")

    def switch_project(self):
        # Show project list dialog
        meta = load_projects_meta()
        projects = meta.get("projects", {})
        
        if not projects:
            QMessageBox.information(self, "Info", "No projects found. Create a new project first.")
            return
        
        # Create dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Switch Project")
        dlg.resize(600, 450)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        
        # Header
        header = QLabel("Select a project:")
        header.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)
        
        # Project list
        list_widget = QListWidget()
        list_widget.setStyleSheet("""
            QListWidget {
                background: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 10px;
                margin: 2px;
                border-radius: 4px;
                border-bottom: 1px solid #3f3f46;
            }
            QListWidget::item:selected {
                background: #4f46e5;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background: #3f3f46;
            }
        """)
        
        def refresh_list():
            """Refresh the project list"""
            list_widget.clear()
            meta = load_projects_meta()
            projects = meta.get("projects", {})
            
            # Sort by last used (most recent first)
            sorted_projects = sorted(
                projects.items(),
                key=lambda x: x[1].get("last_used", ""),
                reverse=True
            )
            
            for proj_path, proj_info in sorted_projects:
                if not Path(proj_path).exists():
                    continue
                display_name = proj_info.get("display_name", Path(proj_path).name)
                last_used = proj_info.get("last_used", "Never")
                if last_used != "Never":
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(last_used)
                        last_used = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                
                # Use simple text without emoji for better compatibility
                item_text = f"{display_name}\n  Path: {proj_path}\n  Last used: {last_used}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, proj_path)
                list_widget.addItem(item)
        
        refresh_list()
        layout.addWidget(list_widget)
        
        # Context Menu for List
        list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        def on_context_menu(pos):
            item = list_widget.itemAt(pos)
            if not item: return
            
            proj_path = item.data(Qt.UserRole)
            menu = QMenu()
            
            act_open = menu.addAction("Open Project")
            act_open.triggered.connect(lambda: (dlg.accept(), self._load_project(Path(proj_path))))
            
            act_reveal = menu.addAction("Reveal in Explorer")
            act_reveal.triggered.connect(lambda: os.startfile(proj_path) if sys.platform=="win32" else None)
            
            menu.addSeparator()
            
            act_rename = menu.addAction("Rename")
            act_rename.triggered.connect(lambda: on_rename_item(item))
            
            act_delete = menu.addAction("Delete")
            act_delete.triggered.connect(lambda: on_delete_item(item))
            
            menu.exec(list_widget.mapToGlobal(pos))
            
        list_widget.customContextMenuRequested.connect(on_context_menu)
        
        # Buttons
        btn_layout1 = QHBoxLayout()
        btn_rename = QPushButton("Rename")
        btn_delete = QPushButton("Delete")
        btn_browse = QPushButton("Browse...")
        
        btn_layout1.addWidget(btn_rename)
        btn_layout1.addWidget(btn_delete)
        btn_layout1.addStretch()
        btn_layout1.addWidget(btn_browse)
        layout.addLayout(btn_layout1)
        
        btn_layout2 = QHBoxLayout()
        btn_ok = QPushButton("Open")
        btn_cancel = QPushButton("Cancel")
        btn_ok.setDefault(True)
        
        btn_layout2.addStretch()
        btn_layout2.addWidget(btn_ok)
        btn_layout2.addWidget(btn_cancel)
        layout.addLayout(btn_layout2)
        
        # Connect buttons
        def on_browse():
            d = QFileDialog.getExistingDirectory(self, "Browse Project Folder", str(DEFAULT_ROOT))
            if d and Path(d).is_dir():
                dlg.accept()
                self._load_project(Path(d))
        
        def on_ok():
            current = list_widget.currentItem()
            if current:
                proj_path = current.data(Qt.UserRole)
                dlg.accept()
                self._load_project(Path(proj_path))
            else:
                QMessageBox.warning(dlg, "Warning", "Please select a project first.")
        
        def on_rename_item(item=None):
            current = item or list_widget.currentItem()
            if not current:
                QMessageBox.warning(dlg, "Warning", "Please select a project to rename.")
                return
            
            proj_path = current.data(Qt.UserRole)
            meta = load_projects_meta()
            old_name = meta["projects"][proj_path].get("display_name", Path(proj_path).name)
            
            new_name, ok = QInputDialog.getText(dlg, "Rename Project", "Enter new project name:", text=old_name)
            if ok and new_name.strip():
                from catalog import save_projects_meta
                meta["projects"][proj_path]["display_name"] = new_name.strip()
                save_projects_meta(meta)
                refresh_list()
                
                # Update current project display if renaming current project
                if str(self.project_dir.resolve()) == proj_path:
                    self.project_display_name = new_name.strip()
                    self.lab_project.setText(self.project_display_name)
                    self.setWindowTitle(f"Ninlab - {self.project_display_name}")
        
        def on_delete_item(item=None):
            current = item or list_widget.currentItem()
            if not current:
                QMessageBox.warning(dlg, "Warning", "Please select a project to delete.")
                return
            
            proj_path = current.data(Qt.UserRole)
            meta = load_projects_meta()
            display_name = meta["projects"][proj_path].get("display_name", Path(proj_path).name)
            
            # Prevent deleting current project
            if str(self.project_dir.resolve()) == proj_path:
                QMessageBox.warning(dlg, "Warning", "Cannot delete the currently open project.")
                return
            
            reply = QMessageBox.question(
                dlg, "Confirm Delete",
                f"Remove project '{display_name}' from the list?\n\nNote: This will only remove it from the list. The project folder and files will not be deleted.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                from catalog import save_projects_meta
                del meta["projects"][proj_path]
                save_projects_meta(meta)
                refresh_list()
                QMessageBox.information(dlg, "Success", f"Project '{display_name}' removed from list.")
        
        btn_browse.clicked.connect(on_browse)
        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dlg.reject)
        btn_rename.clicked.connect(lambda: on_rename_item(None))
        btn_delete.clicked.connect(lambda: on_delete_item(None))
        list_widget.itemDoubleClicked.connect(on_ok)
        
        dlg.exec()

if __name__=="__main__":
    # macOS HiDPI / Retina: rely on Qt6 auto scaling, just adjust rounding and layer usage
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    # if sys.platform == "darwin":
    #     os.environ.setdefault("QT_MAC_WANTS_LAYER", "1") # This can cause blank screens on some macOS/Qt versions
    app=QApplication(sys.argv)
    w=Main()
    sys.exit(app.exec())
