from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QWidget, QFrame, QLabel, QSlider, QToolButton,
    QListWidget, QListWidgetItem, QAbstractItemView
)
from PySide6.QtGui import QIcon, QPixmap, QImage, QColor, QPainter, QFont

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

def filmstrip_add_item(listwidget, thumb_pixmap, userdata):
    it=QListWidgetItem(""); it.setIcon(QIcon(thumb_pixmap)); it.setData(Qt.UserRole, userdata); listwidget.addItem(it)

def badge_star(pixmap: QPixmap, starred: bool) -> QPixmap:
    if not starred: return pixmap
    pm=QPixmap(pixmap); p=QPainter(pm); p.setRenderHint(QPainter.Antialiasing, True)
    r=12; p.setBrush(QColor(255,215,0)); p.setPen(Qt.NoPen); p.drawEllipse(3,3,r,r)
    p.setPen(QColor(30,30,30)); font=QFont(); font.setPointSize(8); font.setBold(True); p.setFont(font)
    p.drawText(3,3,r,r,Qt.AlignCenter,"★"); p.end(); return pm

def qimage_from_u8(arr):
    h,w,_=arr.shape
    return QImage(arr.data, w, h, 3*w, QImage.Format_RGB888)
