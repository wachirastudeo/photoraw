from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QRubberBand, QWidget
from PySide6.QtGui import QPixmap

class CropDialog(QDialog):
    """
    Dialog ง่ายๆ ให้ผู้ใช้ลากกรอบบนภาพเพื่อ crop
    คืนค่า normalized rect: {"x","y","w","h"} หรือ None ถ้ากดยกเลิก
    """
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop")
        self._pixmap = pixmap
        self._rubber = None
        self._origin = QPoint()
        self._current = QRect()

        lay = QVBoxLayout(self)
        self.lab = QLabel()
        self.lab.setPixmap(pixmap)
        self.lab.setAlignment(Qt.AlignCenter)
        self.lab.setStyleSheet("QLabel{background:#111;color:#eee;}")
        lay.addWidget(self.lab)

        btns = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        lay.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        # ให้ QLabel รับ mouse events
        self.lab.setMouseTracking(True)
        self.lab.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.lab:
            if ev.type() == ev.MouseButtonPress and ev.buttons() & Qt.LeftButton:
                self._origin = ev.pos()
                if not self._rubber:
                    self._rubber = QRubberBand(QRubberBand.Rectangle, self.lab)
                self._rubber.setGeometry(QRect(self._origin, ev.pos()))
                self._rubber.show()
                return True
            elif ev.type() == ev.MouseMove and self._rubber and (ev.buttons() & Qt.LeftButton):
                self._rubber.setGeometry(QRect(self._origin, ev.pos()).normalized())
                return True
            elif ev.type() == ev.MouseButtonRelease and self._rubber:
                self._current = self._rubber.geometry().normalized()
                return True
        return super().eventFilter(obj, ev)

    def get_normalized_crop(self):
        if not self._current or self._current.width() < 5 or self._current.height() < 5:
            return None
        # แปลงพิกัดใน QLabel -> พิกัดใน Pixmap ด้วยสเกลเดียวกัน
        lab_rect = self.lab.contentsRect()
        pm = self._pixmap
        pm_w, pm_h = pm.width(), pm.height()
        # คำนวณสเกลที่ QLabel ใช้แสดง pixmap
        ratio = min(lab_rect.width()/pm_w, lab_rect.height()/pm_h)
        disp_w, disp_h = int(pm_w*ratio), int(pm_h*ratio)
        offset_x = (lab_rect.width() - disp_w)//2 + lab_rect.x()
        offset_y = (lab_rect.height() - disp_h)//2 + lab_rect.y()

        sel = self._current
        # จำกัด selection ให้อยู่ในพื้นที่รูป
        x0 = max(offset_x, min(offset_x+disp_w, sel.x()))
        y0 = max(offset_y, min(offset_y+disp_h, sel.y()))
        x1 = max(offset_x, min(offset_x+disp_w, sel.x()+sel.width()))
        y1 = max(offset_y, min(offset_y+disp_h, sel.y()+sel.height()))
        if x1 <= x0 or y1 <= y0:
            return None

        # map กลับไปเป็นพิกัดในภาพ
        img_x0 = (x0 - offset_x) / disp_w
        img_y0 = (y0 - offset_y) / disp_h
        img_x1 = (x1 - offset_x) / disp_w
        img_y1 = (y1 - offset_y) / disp_h

        x = max(0.0, min(1.0, img_x0))
        y = max(0.0, min(1.0, img_y0))
        w = max(0.0, min(1.0, img_x1 - img_x0))
        h = max(0.0, min(1.0, img_y1 - img_y0))

        if w < 0.01 or h < 0.01:
            return None
        return {"x": x, "y": y, "w": w, "h": h}
