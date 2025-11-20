from PySide6.QtCore import Qt, QSize, QRect, QPoint
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QWidget, QFrame, QLabel, QSlider, QToolButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QLayout, QSizePolicy, QStyle
)
from PySide6.QtGui import QIcon, QPixmap, QImage, QColor, QPainter, QFont, QLinearGradient, QBrush, QPen, QPainterPath

def create_app_icon(size=64):
    """Generates a programmatic app icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Background: Rounded Rect with Gradient
    grad_bg = QLinearGradient(0, 0, size, size)
    grad_bg.setColorAt(0.0, QColor("#4338ca")) # Indigo-700
    grad_bg.setColorAt(1.0, QColor("#312e81")) # Indigo-900
    
    painter.setBrush(QBrush(grad_bg))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, size, size, size*0.22, size*0.22)
    
    # Lens Element: Central Circle
    center = size / 2
    radius = size * 0.35
    
    grad_lens = QLinearGradient(0, 0, size, size)
    grad_lens.setColorAt(0.0, QColor("#1e1b4b")) # Indigo-950
    grad_lens.setColorAt(1.0, QColor("#312e81")) # Indigo-900
    
    painter.setBrush(QBrush(grad_lens))
    painter.setPen(QPen(QColor("#6366f1"), size*0.05)) # Indigo-500 ring
    painter.drawEllipse(QPoint(center, center), radius, radius)
    
    # Reflection/Shine
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255, 40))
    painter.drawEllipse(QPoint(center - radius*0.3, center - radius*0.3), radius*0.25, radius*0.25)
    
    painter.end()
    return QIcon(pixmap)

class DoubleClickSlider(QSlider):
    def __init__(self, orientation, on_double_click=None, parent=None):
        super().__init__(orientation, parent)
        self.on_double_click = on_double_click

    def mouseDoubleClickEvent(self, event):
        if self.on_double_click:
            self.on_double_click()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

def add_slider(form: QFormLayout, title_widget, key: str, lo: float, hi: float, val: float, step=0.01,
               on_change=None, on_reset=None, color_hex=None, on_press=None, on_release=None):
    row = QHBoxLayout(); row.setContentsMargins(0,0,0,0)
    
    # Define reset action
    def do_reset():
        sld.blockSignals(True)
        sld.setValue(int(val/step))
        sld.blockSignals(False)
        if on_reset: on_reset(key)
        # Update label manually since signal was blocked
        lab.setText(f"{val:.2f}")

    # Use custom DoubleClickSlider
    sld = DoubleClickSlider(Qt.Horizontal, on_double_click=do_reset)
    sld.setMinimum(int(lo/step)); sld.setMaximum(int(hi/step)); sld.setValue(int(val/step))
    sld.setSingleStep(1); sld.setPageStep(5); sld.setTracking(True)
    if on_press: sld.sliderPressed.connect(on_press)
    if on_release: sld.sliderReleased.connect(on_release)

    # --- [REVISED] Create Gradient Stylesheet based on Slider Type ---
    gradient_style = ""
    # Temperature: Blue -> Yellow/Orange
    if key == "temperature":
        gradient_style = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:0.5 #ffffff, stop:1 #eab308);"
    # Tint: Green -> Magenta
    elif key == "tint":
        gradient_style = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22c55e, stop:0.5 #ffffff, stop:1 #d946ef);"
    # Saturation / Vibrance: Gray -> Vibrant Red
    elif key in ("saturation", "vibrance"):
        gradient_style = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9ca3af, stop:1 #ef4444);"
    # HSL - Hue (Full Spectrum)
    elif key.startswith("h_"):
        gradient_style = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff0000, stop:0.16 #ffff00, stop:0.33 #00ff00, stop:0.5 #00ffff, stop:0.66 #0000ff, stop:0.83 #ff00ff, stop:1 #ff0000);"
    # HSL - Saturation
    elif key.startswith("s_") and color_hex:
        gradient_style = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9ca3af, stop:1 {color_hex});"
    # HSL - Luminance
    elif key.startswith("l_") and color_hex:
        gradient_style = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #000000, stop:0.5 {color_hex}, stop:1 #ffffff);"

    # Apply Stylesheet if Gradient exists
    if gradient_style:
        sld.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 1px solid #52525b;
                height: 6px;
                background: {gradient_style};
                margin: 2px 0;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #f4f4f5;
                border: 1px solid #52525b;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            /* IMPORTANT: Make sub-page transparent to show the gradient groove */
            QSlider::sub-page:horizontal {{
                background: transparent;
            }}
        """)
    # --- End Revised Section ---

    lab = QLabel(f"{val:.2f}")
    sld.valueChanged.connect(lambda v: (lab.setText(f"{v*step:.2f}"), on_change and on_change(key, v*step)))
    btn = QToolButton(); btn.setText("↺"); btn.setToolTip("Reset")
    btn.clicked.connect(do_reset)
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

def filmstrip_add_item(listwidget, thumb_pixmap, userdata):
    it=QListWidgetItem(""); it.setIcon(QIcon(thumb_pixmap)); it.setData(Qt.UserRole, userdata); listwidget.addItem(it)

def badge_star(pixmap: QPixmap, starred: bool) -> QPixmap:
    if not starred: return pixmap
    pm=QPixmap(pixmap); p=QPainter(pm); p.setRenderHint(QPainter.Antialiasing, True)
    
    # Minimal Vector Star
    star_path = QPainterPath()
    cx, cy = 12, 12  # Center position
    outer_radius = 8
    inner_radius = 4
    angle = -90 # Start at top
    
    import math
    points = []
    for i in range(10):
        r = outer_radius if i % 2 == 0 else inner_radius
        rad = math.radians(angle + i * 36)
        x = cx + r * math.cos(rad)
        y = cy + r * math.sin(rad)
        if i == 0: star_path.moveTo(x, y)
        else: star_path.lineTo(x, y)
    star_path.closeSubpath()

    # Drop shadow for visibility on light backgrounds
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 80))
    p.translate(1, 1)
    p.drawPath(star_path)
    
    # Main Star
    p.translate(-1, -1)
    p.setBrush(QColor("#FFD700")) # Gold
    p.drawPath(star_path)
    
    p.end(); return pm

def qimage_from_u8(arr):
    h,w,_=arr.shape
    return QImage(arr.data, w, h, 3*w, QImage.Format_RGB888)

class FlowLayout(QLayout):
    """Simple flow layout so toolbar widgets can wrap on smaller screens."""
    def __init__(self, parent=None, margin=0, hSpacing=8, vSpacing=6):
        super().__init__(parent)
        self._items=[]
        self._hSpacing=hSpacing
        self._vSpacing=vSpacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.sizeHint())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _h_spacing(self):
        return self._spacing(self._hSpacing, QStyle.PM_LayoutHorizontalSpacing)

    def _v_spacing(self):
        return self._spacing(self._vSpacing, QStyle.PM_LayoutVerticalSpacing)

    def _spacing(self, space, pm):
        if space >= 0:
            return space
        parent = self.parentWidget()
        if parent is None:
            return 6
        return parent.style().pixelMetric(pm, None, parent)

    def _do_layout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        line_height = 0
        space_x = self._h_spacing()
        space_y = self._v_spacing()
        max_width = rect.width()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + space_x
            if line_height > 0 and next_x - rect.x() > max_width:
                x = rect.x()
                y += line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0
            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y()
