from PySide6.QtCore import Qt, QRect, QPoint, QSize, QRectF

from PySide6.QtGui import QPixmap, QPainter, QColor, QPainterPath


from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QHBoxLayout, QComboBox, QWidget, QSizePolicy, QMessageBox
from PySide6.QtCore import QEvent

class CropOverlay(QWidget):
    """Widget สำหรับวาดทับบน QLabel เพื่อแสดงกรอบ Crop และพื้นที่มืด"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.crop_rect = QRect()
        self.handles = {}
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_crop_rect(self, rect):
        self.crop_rect = rect
        self.update_handles()
        self.update()

    def update_handles(self):
        self.handles = self.get_handles(self.crop_rect)

    def get_handles(self, rect):
        if rect.isNull() or not rect.isValid(): return {}
        size = 10
        hs = size // 2
        return {
            "top_left": QRect(rect.left() - hs, rect.top() - hs, size, size),
            "top_right": QRect(rect.right() - hs, rect.top() - hs, size, size),
            "bottom_left": QRect(rect.left() - hs, rect.bottom() - hs, size, size),
            "bottom_right": QRect(rect.right() - hs, rect.bottom() - hs, size, size),
            "top": QRect(rect.center().x() - hs, rect.top() - hs, size, size),
            "bottom": QRect(rect.center().x() - hs, rect.bottom() - hs, size, size),
            "left": QRect(rect.left() - hs, rect.center().y() - hs, size, size),
            "right": QRect(rect.right() - hs, rect.center().y() - hs, size, size),
        }

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.crop_rect.isNull() and self.crop_rect.isValid():
            painter = QPainter(self)
            # วาดพื้นที่มืดรอบๆ กรอบ Crop
            outer_path = QPainterPath()
            outer_path.addRect(self.rect())
            inner_path = QPainterPath()
            inner_path.addRect(self.crop_rect)
            dim_path = outer_path.subtracted(inner_path)
            painter.fillPath(dim_path, QColor(0, 0, 0, 150))  # Color(0, 0, 0, 150) คือสีเทาที่มีความโปร่งแสง

            # วาดกรอบสีขาวรอบ selection
            pen = painter.pen()
            pen.setColor(Qt.white)
            pen.setWidth(1)
            pen.setStyle(Qt.DotLine)
            painter.setPen(pen)
            painter.drawRect(self.crop_rect)

            # วาดเส้น Grid (Rule of Thirds)
            pen.setStyle(Qt.SolidLine)
            pen.setColor(QColor(255, 255, 255, 100))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(self.crop_rect.left(), self.crop_rect.top() + self.crop_rect.height() // 3, self.crop_rect.right(), self.crop_rect.top() + self.crop_rect.height() // 3)
            painter.drawLine(self.crop_rect.left(), self.crop_rect.top() + 2 * self.crop_rect.height() // 3, self.crop_rect.right(), self.crop_rect.top() + 2 * self.crop_rect.height() // 3)
            painter.drawLine(self.crop_rect.left() + self.crop_rect.width() // 3, self.crop_rect.top(), self.crop_rect.left() + self.crop_rect.width() // 3, self.crop_rect.bottom())
            painter.drawLine(self.crop_rect.left() + 2 * self.crop_rect.width() // 3, self.crop_rect.top(), self.crop_rect.left() + 2 * self.crop_rect.width() // 3, self.crop_rect.bottom())

            # วาด Handles
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 220))
            for handle in self.handles.values():
                painter.drawRect(handle)


class CropDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop")
        self.setMinimumSize(800, 600)

        self._pixmap = pixmap  # Store the original pixmap
        self.mode = None  # None, 'drawing', 'moving', 'resizing'
        self.active_handle = None
        self.initial_rect = QRect()
        self.aspect_ratio = None  # None for free, float for ratio (w/h)

        self._origin = QPoint()
        self._current = QRect()

        lay = QVBoxLayout(self)
        self.lab = QLabel()
        self.lab.setPixmap(pixmap)
        self.lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lab.setAlignment(Qt.AlignCenter)
        self.lab.setStyleSheet("QLabel{background:#111;color:#eee;}")
        lay.addWidget(self.lab)

        # Aspect Ratio controls
        aspect_bar = QHBoxLayout()
        aspect_bar.addWidget(QLabel("Aspect Ratio:"))
        self.cmb_aspect = QComboBox()
        self.cmb_aspect.addItems(["Free", "Original", "1:1", "4:3", "3:2", "16:9"])
        self.cmb_aspect.currentTextChanged.connect(self._on_aspect_ratio_changed)  # connect the change
        aspect_bar.addStretch(1)
        aspect_bar.addWidget(self.cmb_aspect)
        lay.addLayout(aspect_bar)

        # Overlay สำหรับวาดกรอบ Crop
        self.overlay = CropOverlay(self.lab)
        self.overlay.show()
        self.overlay.setGeometry(self.lab.rect())

        # Create buttons for OK, Cancel, and Reset
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        lay.addWidget(btns)
        btns.accepted.connect(self.accept_crop)
        btns.rejected.connect(self.reject)
        # Only the Reset button should clear the crop; OK/Cancel must not reset before validation
        reset_btn = btns.button(QDialogButtonBox.Reset)
        if reset_btn:
            reset_btn.clicked.connect(self.reset_all)

        # ให้ QLabel รับ mouse events
        self.lab.setMouseTracking(True)  # Important for cursor changes
        self.lab.installEventFilter(self)

        self.setCursor(Qt.CrossCursor)

    def _on_aspect_ratio_changed(self, text):
        """เมื่อผู้ใช้เลือกอัตราส่วนจาก combo box"""
        if text == "Free":
            self.aspect_ratio = None
        elif text == "Original":
            self.aspect_ratio = self._pixmap.width() / self._pixmap.height()
        elif text == "1:1":
            self.aspect_ratio = 1.0
        elif text == "4:3":
            self.aspect_ratio = 4.0 / 3.0
        elif text == "3:2":
            self.aspect_ratio = 3.0 / 2.0
        elif text == "16:9":
            self.aspect_ratio = 16.0 / 9.0
        else:
            self.aspect_ratio = None

        if self.aspect_ratio and not self._current.isNull() and self._current.isValid():
            self._current = self.adjust_rect_aspect(self._current, self.aspect_ratio)
            self.overlay.set_crop_rect(self._current)

    def adjust_rect_aspect(self, rect, ratio):
        """Adjust rectangle dimensions to match aspect ratio"""
        if ratio is None: return rect
        w, h = rect.width(), rect.height()
        if w == 0 or h == 0: return rect
        
        current_ratio = w / h
        
        if current_ratio > ratio:
            # Current is wider than target -> reduce width
            new_w = int(h * ratio)
            new_h = h
        else:
            # Current is taller than target -> reduce height
            new_w = w
            new_h = int(w / ratio)
            
        return QRect(rect.x(), rect.y(), new_w, new_h)

    def reset_all(self):
        """รีเซ็ตค่าทั้งหมดกลับไปที่ค่าเริ่มต้น"""
        self._current = QRect()  # Reset the crop rectangle
        self.overlay.set_crop_rect(self._current)  # Update overlay

        # Reset aspect ratio to "Free"
        self.cmb_aspect.setCurrentText("Free")
        self.aspect_ratio = None

        # Reset any other settings you need, such as the origin point
        self._origin = QPoint()
        self.mode = None

        # Optionally, reset any other UI elements like sliders or labels
        self.update()  # Refresh the UI

    def eventFilter(self, obj, ev):
        """Handle mouse events to allow drawing and moving of the crop area."""
        if obj is self.lab:
            if ev.type() == QEvent.MouseMove and ev.buttons() & Qt.LeftButton:
                # Update the crop area while dragging
                delta = ev.pos() - self._origin
                if self.mode == 'drawing':
                    self._current = QRect(self._origin, ev.pos()).normalized()
                    if self.aspect_ratio:
                        self._current = self.adjust_rect_aspect(self._current, self.aspect_ratio)
                elif self.mode == 'moving' and self._current.contains(ev.pos()):
                    self._current.moveTopLeft(ev.pos() - self._origin)
                self.overlay.set_crop_rect(self._current)
                return True

            elif ev.type() == QEvent.MouseButtonPress and ev.buttons() & Qt.LeftButton:
                # Set origin when mouse button is pressed
                self._origin = ev.pos()
                if self._current.contains(ev.pos()):
                    self.mode = 'moving'
                else:
                    self.mode = 'drawing'
                    self._current = QRect(self._origin, QSize())  # Start drawing from click position
                return True

            elif ev.type() == QEvent.MouseButtonRelease:
                self.mode = None
                return True

            elif ev.type() == QEvent.Resize:
                # Keep overlay in sync with label size when window resizes
                self.overlay.setGeometry(self.lab.rect())
                self.overlay.update_handles()

        return super().eventFilter(obj, ev)

    def accept_crop(self):
        """When OK is pressed, return the normalized crop values."""
        normalized_crop = self.get_normalized_crop()
        if normalized_crop:
            self.accept()  # Close the dialog and send the crop data via `accept()`
        else:
            QMessageBox.warning(self, "Error", "Invalid crop area!")

    def get_normalized_crop(self):
        """คำนวณค่าพิกัดของการครอบในอัตราส่วน normalized"""
        if self._current.isNull() or self._current.width() < 5 or self._current.height() < 5:
            return None

        lab_rect = self.lab.contentsRect()  # ขนาดของ QLabel
        pm = self._pixmap
        pm_w, pm_h = pm.width(), pm.height()  # ขนาดของภาพจริง

        ratio = min(lab_rect.width() / pm_w, lab_rect.height() / pm_h)
        disp_w, disp_h = int(pm_w * ratio), int(pm_h * ratio)
        
        offset_x = (lab_rect.width() - disp_w) // 2 + lab_rect.x()
        offset_y = (lab_rect.height() - disp_h) // 2 + lab_rect.y()

        # Convert crop rect from label coordinates to image coordinates (normalized)
        x = (self._current.x() - offset_x) / disp_w
        y = (self._current.y() - offset_y) / disp_h
        w = self._current.width() / disp_w
        h = self._current.height() / disp_h

        # Clamp values to be within [0, 1] and handle intersections
        final_x = max(0.0, min(1.0, x))
        final_y = max(0.0, min(1.0, y))
        final_w = max(0.0, min(1.0 - final_x, w))
        final_h = max(0.0, min(1.0 - final_y, h))

        if w < 0.01 or h < 0.01:
            return None
        return {"x": final_x, "y": final_y, "w": final_w, "h": final_h}

