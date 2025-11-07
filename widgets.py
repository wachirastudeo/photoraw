# widgets.py
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QGroupBox, QFormLayout, QHBoxLayout, QSlider, QLabel, QToolButton,
    QListWidget, QListWidgetItem, QAbstractItemView
)
from PySide6.QtGui import QIcon, QPixmap

def add_slider(form: QFormLayout, title: str, key: str, lo: float, hi: float, val: float, step=0.01,
               on_change=None, on_reset=None):
    row = QHBoxLayout()
    sld = QSlider(Qt.Horizontal)
    sld.setMinimum(int(lo/step)); sld.setMaximum(int(hi/step)); sld.setValue(int(val/step))
    sld.setSingleStep(1); sld.setPageStep(5); sld.setTracking(False)
    lab = QLabel(f"{val:.2f}")
    sld.valueChanged.connect(lambda v: (lab.setText(f"{v*step:.2f}"),
                                        on_change and on_change(key, v*step)))
    row.addWidget(sld); row.addWidget(lab)
    btn = QToolButton(); btn.setText("↺")
    btn.clicked.connect(lambda: (sld.blockSignals(True), sld.setValue(int(val/step)), sld.blockSignals(False),
                                 on_reset and on_reset(key)))
    row.addWidget(btn)
    form.addRow(title, row)
    return sld, lab

def create_filmstrip(icon_size=QSize(96, 64), height=80):
    lw = QListWidget()
    lw.setViewMode(QListWidget.IconMode)
    lw.setMovement(QListWidget.Static)
    lw.setFlow(QListWidget.LeftToRight)
    lw.setWrapping(False)  # ไม่ตัดบรรทัด → เลื่อนได้เฉพาะซ้าย-ขวา
    lw.setResizeMode(QListWidget.Adjust)
    lw.setIconSize(icon_size)
    lw.setFixedHeight(height)
    lw.setSpacing(6)

    # เลื่อนเฉพาะซ้าย-ขวา (ปิดสกอร์บาร์แนวตั้ง)
    lw.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    lw.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    # เลือกหลายรายการ (Ctrl/Shift/Ctrl+A)
    lw.setSelectionMode(QAbstractItemView.ExtendedSelection)
    return lw

def filmstrip_add_item(listwidget: QListWidget, thumb_pixmap: QPixmap, userdata):
    item = QListWidgetItem("")   # ไม่แสดงชื่อ
    item.setIcon(QIcon(thumb_pixmap))
    item.setData(Qt.UserRole, userdata)
    listwidget.addItem(item)
