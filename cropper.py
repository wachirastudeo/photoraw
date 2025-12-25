import math
from PySide6.QtCore import Qt, QRect, QPoint, QSize, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QColor, QPainterPath, QTransform, QPen, QImage, QCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QHBoxLayout, 
    QComboBox, QWidget, QSizePolicy, QMessageBox, QSlider, QCheckBox
)
from PySide6.QtCore import QEvent


def calculate_largest_inscribed_rect(img_width, img_height, angle_deg):
    """
    Calculate the largest axis-aligned rectangle that fits inside
    a rotated rectangle (the original image bounds).
    
    Returns (x, y, width, height) as normalized values (0-1).
    """
    if abs(angle_deg) < 0.001:
        return (0.0, 0.0, 1.0, 1.0)
    
    angle_rad = abs(math.radians(angle_deg))
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    
    w = img_width
    h = img_height
    
    if w <= 0 or h <= 0:
        return (0.0, 0.0, 1.0, 1.0)
    
    if abs(sin_a) < 0.001:
        return (0.0, 0.0, 1.0, 1.0)
    
    # Calculate inscribed rectangle dimensions
    if cos_a > 0:
        inscribed_w = (w * cos_a - h * sin_a) 
        inscribed_h = (h * cos_a - w * sin_a)
        
        if inscribed_w <= 0 or inscribed_h <= 0:
            inscribed_w = w * (cos_a ** 2)
            inscribed_h = h * (cos_a ** 2)
    else:
        inscribed_w = w * 0.5
        inscribed_h = h * 0.5
    
    inscribed_w = max(inscribed_w, w * 0.1)
    inscribed_h = max(inscribed_h, h * 0.1)
    
    offset_x = (w - inscribed_w) / 2
    offset_y = (h - inscribed_h) / 2
    
    norm_x = offset_x / w
    norm_y = offset_y / h
    norm_w = inscribed_w / w
    norm_h = inscribed_h / h
    
    return (norm_x, norm_y, norm_w, norm_h)


class StraightenOverlay(QWidget):
    """Widget for drawing the straighten overlay with rotated image preview"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.crop_rect = QRect()
        self.handles = {}
        self.angle = 0.0
        self.rotated_pixmap = None
        self.original_pixmap = None
        self.display_rect = QRect()
        self.show_grid = True
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        
    def set_angle(self, angle):
        self.angle = angle
        self.update()
        
    def set_pixmaps(self, original, rotated, display_rect):
        self.original_pixmap = original
        self.rotated_pixmap = rotated
        self.display_rect = display_rect
        self.update()

    def set_crop_rect(self, rect):
        self.crop_rect = rect
        self.update_handles()
        self.update()

    def update_handles(self):
        self.handles = self.get_handles(self.crop_rect)

    def get_handles(self, rect):
        if rect.isNull() or not rect.isValid():
            return {}
        size = 14
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
    
    def get_handle_at(self, pos):
        """Return handle name at position, or None"""
        for name, rect in self.handles.items():
            if rect.contains(pos):
                return name
        return None
    
    def get_cursor_for_handle(self, handle_name):
        """Return appropriate cursor for a handle"""
        if handle_name in ("top_left", "bottom_right"):
            return Qt.SizeFDiagCursor
        elif handle_name in ("top_right", "bottom_left"):
            return Qt.SizeBDiagCursor
        elif handle_name in ("top", "bottom"):
            return Qt.SizeVerCursor
        elif handle_name in ("left", "right"):
            return Qt.SizeHorCursor
        return Qt.ArrowCursor

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Fill background with dark gray
        painter.fillRect(self.rect(), QColor(30, 30, 30))
        
        # Draw the rotated image if available
        if self.rotated_pixmap and not self.rotated_pixmap.isNull():
            rx = (self.width() - self.rotated_pixmap.width()) // 2
            ry = (self.height() - self.rotated_pixmap.height()) // 2
            painter.drawPixmap(rx, ry, self.rotated_pixmap)
        
        # Draw crop box and grid
        if not self.crop_rect.isNull() and self.crop_rect.isValid():
            # Draw dark overlay outside crop area
            outer_path = QPainterPath()
            outer_path.addRect(QRectF(self.rect()))
            inner_path = QPainterPath()
            inner_path.addRect(QRectF(self.crop_rect))
            dim_path = outer_path.subtracted(inner_path)
            painter.fillPath(dim_path, QColor(0, 0, 0, 150))

            # Draw white border around crop area
            pen = QPen(Qt.white)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(self.crop_rect)

            # Draw Grid (Rule of Thirds + more lines for alignment)
            if self.show_grid:
                pen.setWidth(1)
                pen.setColor(QColor(255, 255, 255, 100))
                painter.setPen(pen)
                
                cr = self.crop_rect
                
                # Rule of Thirds (3x3 grid)
                for i in range(1, 3):
                    # Vertical lines
                    x = cr.left() + (cr.width() * i) // 3
                    painter.drawLine(x, cr.top(), x, cr.bottom())
                    # Horizontal lines
                    y = cr.top() + (cr.height() * i) // 3
                    painter.drawLine(cr.left(), y, cr.right(), y)
                
                # Center crosshair
                pen.setColor(QColor(255, 255, 255, 60))
                painter.setPen(pen)
                cx = cr.center().x()
                cy = cr.center().y()
                painter.drawLine(cx, cr.top(), cx, cr.bottom())
                painter.drawLine(cr.left(), cy, cr.right(), cy)

            # Draw handles
            painter.setPen(Qt.NoPen)
            for name, handle in self.handles.items():
                # Corner handles are larger and white
                if "top" in name or "bottom" in name or "left" in name or "right" in name:
                    if "_" in name:  # Corner handles
                        painter.setBrush(QColor(255, 255, 255, 255))
                    else:  # Edge handles
                        painter.setBrush(QColor(255, 255, 255, 200))
                    painter.drawRect(handle)


class CropDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None, initial_angle=0.0):
        super().__init__(parent)
        self.setWindowTitle("Crop & Straighten")
        self.setMinimumSize(900, 700)

        self._original_pixmap = pixmap
        self._angle = initial_angle
        self._constrain_to_image = True
        
        self.mode = None  # 'drawing', 'moving', 'resizing'
        self.active_handle = None
        self.aspect_ratio = None

        self._origin = QPoint()
        self._current = QRect()
        self._display_rect = QRect()
        self._drag_start = QPoint()
        self._initial_rect = QRect()

        lay = QVBoxLayout(self)
        
        # Main preview area
        self.overlay = StraightenOverlay()
        self.overlay.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.overlay.setMinimumSize(600, 400)
        lay.addWidget(self.overlay)
        
        # Controls bar
        controls = QHBoxLayout()
        
        # Aspect Ratio
        controls.addWidget(QLabel("Aspect:"))
        self.cmb_aspect = QComboBox()
        self.cmb_aspect.addItems(["Free", "Original", "1:1", "4:3", "3:2", "16:9"])
        self.cmb_aspect.currentTextChanged.connect(self._on_aspect_ratio_changed)
        controls.addWidget(self.cmb_aspect)
        
        controls.addSpacing(20)
        
        # Angle slider
        controls.addWidget(QLabel("Angle:"))
        self.angle_slider = QSlider(Qt.Horizontal)
        self.angle_slider.setRange(-150, 150)  # -15.0 to +15.0 degrees
        self.angle_slider.setValue(int(initial_angle * 10))
        self.angle_slider.setFixedWidth(200)
        self.angle_slider.valueChanged.connect(self._on_angle_changed)
        controls.addWidget(self.angle_slider)
        
        self.angle_label = QLabel(f"{initial_angle:.1f}°")
        self.angle_label.setFixedWidth(50)
        controls.addWidget(self.angle_label)
        
        controls.addSpacing(20)
        
        # Constrain checkbox
        self.chk_constrain = QCheckBox("Constrain to Image")
        self.chk_constrain.setChecked(True)
        self.chk_constrain.toggled.connect(self._on_constrain_changed)
        controls.addWidget(self.chk_constrain)
        
        # Grid checkbox
        self.chk_grid = QCheckBox("Show Grid")
        self.chk_grid.setChecked(True)
        self.chk_grid.toggled.connect(self._on_grid_changed)
        controls.addWidget(self.chk_grid)
        
        controls.addStretch(1)
        lay.addLayout(controls)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        lay.addWidget(btns)
        btns.accepted.connect(self.accept_crop)
        btns.rejected.connect(self.reject)
        reset_btn = btns.button(QDialogButtonBox.Reset)
        if reset_btn:
            reset_btn.clicked.connect(self.reset_all)

        # Enable mouse events on overlay
        self.overlay.installEventFilter(self)
        
        self.setCursor(Qt.CrossCursor)
        
        # Initial update
        self._update_rotated_preview()

    def _on_angle_changed(self, value):
        self._angle = value / 10.0
        self.angle_label.setText(f"{self._angle:.1f}°")
        self._update_rotated_preview()

    def _on_constrain_changed(self, checked):
        self._constrain_to_image = checked
        self._update_rotated_preview()
    
    def _on_grid_changed(self, checked):
        self.overlay.show_grid = checked
        self.overlay.update()

    def _update_rotated_preview(self):
        """Update the rotated image preview and auto-crop bounds"""
        pm = self._original_pixmap
        if pm.isNull():
            return
            
        overlay_w = self.overlay.width()
        overlay_h = self.overlay.height()
        
        if overlay_w <= 0 or overlay_h <= 0:
            overlay_w = 600
            overlay_h = 400
        
        # Create rotated pixmap
        if abs(self._angle) > 0.01:
            transform = QTransform()
            transform.rotate(self._angle)
            rotated = pm.transformed(transform, Qt.SmoothTransformation)
        else:
            rotated = pm
        
        # Scale to fit overlay
        scaled = rotated.scaled(
            overlay_w - 40, overlay_h - 40,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Calculate display rect (centered)
        dx = (overlay_w - scaled.width()) // 2
        dy = (overlay_h - scaled.height()) // 2
        self._display_rect = QRect(dx, dy, scaled.width(), scaled.height())
        
        # Pass pixmaps to overlay
        self.overlay.set_angle(self._angle)
        self.overlay.set_pixmaps(pm, scaled, self._display_rect)
        
        # Calculate auto crop bounds if constrained
        if self._constrain_to_image and abs(self._angle) > 0.01:
            crop_bounds = calculate_largest_inscribed_rect(
                pm.width(), pm.height(), self._angle
            )
            
            angle_rad = abs(math.radians(self._angle))
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            
            rot_w = pm.width() * cos_a + pm.height() * sin_a
            rot_h = pm.height() * cos_a + pm.width() * sin_a
            
            scale = min(scaled.width() / rot_w, scaled.height() / rot_h)
            
            cx = dx + scaled.width() / 2
            cy = dy + scaled.height() / 2
            
            inscribed_w = crop_bounds[2] * pm.width()
            inscribed_h = crop_bounds[3] * pm.height()
            
            disp_crop_w = inscribed_w * scale
            disp_crop_h = inscribed_h * scale
            
            crop_x = cx - disp_crop_w / 2
            crop_y = cy - disp_crop_h / 2
            
            self._current = QRect(
                int(crop_x), int(crop_y),
                int(disp_crop_w), int(disp_crop_h)
            )
        else:
            if self._current.isNull() or not self._current.isValid():
                self._current = self._display_rect
        
        self.overlay.set_crop_rect(self._current)

    def _on_aspect_ratio_changed(self, text):
        if text == "Free":
            self.aspect_ratio = None
        elif text == "Original":
            self.aspect_ratio = self._original_pixmap.width() / self._original_pixmap.height()
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
        if ratio is None:
            return rect
        w, h = rect.width(), rect.height()
        if w == 0 or h == 0:
            return rect
        
        current_ratio = w / h
        if current_ratio > ratio:
            new_w = int(h * ratio)
            new_h = h
        else:
            new_w = w
            new_h = int(w / ratio)
        
        cx, cy = rect.center().x(), rect.center().y()
        return QRect(cx - new_w // 2, cy - new_h // 2, new_w, new_h)

    def reset_all(self):
        self._current = QRect()
        self._angle = 0.0
        self.angle_slider.setValue(0)
        self.angle_label.setText("0.0°")
        self.cmb_aspect.setCurrentText("Free")
        self.aspect_ratio = None
        self.chk_constrain.setChecked(True)
        self._origin = QPoint()
        self.mode = None
        self._update_rotated_preview()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rotated_preview()

    def eventFilter(self, obj, ev):
        if obj is self.overlay:
            pos = ev.pos()
            
            # Mouse move for cursor and dragging
            if ev.type() == QEvent.MouseMove:
                if self.mode is None:
                    # Just hovering - update cursor
                    handle = self.overlay.get_handle_at(pos)
                    if handle:
                        self.overlay.setCursor(self.overlay.get_cursor_for_handle(handle))
                    elif self._current.isValid() and self._current.contains(pos):
                        self.overlay.setCursor(Qt.SizeAllCursor)
                    else:
                        self.overlay.setCursor(Qt.CrossCursor)
                
                elif ev.buttons() & Qt.LeftButton:
                    if self.mode == 'drawing':
                        self._current = QRect(self._origin, pos).normalized()
                        if self.aspect_ratio:
                            self._current = self.adjust_rect_aspect(self._current, self.aspect_ratio)
                    
                    elif self.mode == 'moving':
                        delta = pos - self._drag_start
                        new_rect = QRect(self._initial_rect)
                        new_rect.moveTopLeft(self._initial_rect.topLeft() + delta)
                        self._current = new_rect
                    
                    elif self.mode == 'resizing':
                        self._resize_rect(pos)
                    
                    self.overlay.set_crop_rect(self._current)
                return True

            elif ev.type() == QEvent.MouseButtonPress and ev.buttons() & Qt.LeftButton:
                self._origin = pos
                self._drag_start = pos
                self._initial_rect = QRect(self._current)
                
                # Check if clicking on a handle
                handle = self.overlay.get_handle_at(pos)
                if handle:
                    self.mode = 'resizing'
                    self.active_handle = handle
                elif self._current.isValid() and self._current.contains(pos):
                    self.mode = 'moving'
                else:
                    self.mode = 'drawing'
                    self._current = QRect(self._origin, QSize())
                return True

            elif ev.type() == QEvent.MouseButtonRelease:
                self.mode = None
                self.active_handle = None
                return True

        return super().eventFilter(obj, ev)
    
    def _resize_rect(self, pos):
        """Resize the crop rect based on active handle"""
        if not self.active_handle:
            return
        
        rect = QRect(self._initial_rect)
        delta = pos - self._drag_start
        
        # Handle each resize direction
        if 'left' in self.active_handle:
            new_left = rect.left() + delta.x()
            if new_left < rect.right() - 20:
                rect.setLeft(new_left)
        
        if 'right' in self.active_handle:
            new_right = rect.right() + delta.x()
            if new_right > rect.left() + 20:
                rect.setRight(new_right)
        
        if 'top' in self.active_handle:
            new_top = rect.top() + delta.y()
            if new_top < rect.bottom() - 20:
                rect.setTop(new_top)
        
        if 'bottom' in self.active_handle:
            new_bottom = rect.bottom() + delta.y()
            if new_bottom > rect.top() + 20:
                rect.setBottom(new_bottom)
        
        # Apply aspect ratio constraint if needed
        if self.aspect_ratio:
            rect = self.adjust_rect_aspect(rect, self.aspect_ratio)
        
        self._current = rect

    def accept_crop(self):
        normalized = self.get_normalized_crop()
        if normalized:
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "Invalid crop area!")

    def get_normalized_crop(self):
        """Return normalized crop coordinates relative to the ROTATED image"""
        if self._current.isNull() or self._current.width() < 5 or self._current.height() < 5:
            return None
        
        dr = self._display_rect
        if dr.width() <= 0 or dr.height() <= 0:
            return None
        
        x = (self._current.x() - dr.x()) / dr.width()
        y = (self._current.y() - dr.y()) / dr.height()
        w = self._current.width() / dr.width()
        h = self._current.height() / dr.height()
        
        final_x = max(0.0, min(1.0, x))
        final_y = max(0.0, min(1.0, y))
        final_w = max(0.0, min(1.0 - final_x, w))
        final_h = max(0.0, min(1.0 - final_y, h))
        
        if final_w < 0.01 or final_h < 0.01:
            return None
        
        return {"x": final_x, "y": final_y, "w": final_w, "h": final_h}
    
    def get_angle(self):
        """Return the straighten angle"""
        return self._angle


# Keep old class for compatibility
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
            outer_path = QPainterPath()
            outer_path.addRect(self.rect())
            inner_path = QPainterPath()
            inner_path.addRect(self.crop_rect)
            dim_path = outer_path.subtracted(inner_path)
            painter.fillPath(dim_path, QColor(0, 0, 0, 150))

            pen = painter.pen()
            pen.setColor(Qt.white)
            pen.setWidth(1)
            pen.setStyle(Qt.DotLine)
            painter.setPen(pen)
            painter.drawRect(self.crop_rect)

            pen.setStyle(Qt.SolidLine)
            pen.setColor(QColor(255, 255, 255, 100))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(self.crop_rect.left(), self.crop_rect.top() + self.crop_rect.height() // 3, self.crop_rect.right(), self.crop_rect.top() + self.crop_rect.height() // 3)
            painter.drawLine(self.crop_rect.left(), self.crop_rect.top() + 2 * self.crop_rect.height() // 3, self.crop_rect.right(), self.crop_rect.top() + 2 * self.crop_rect.height() // 3)
            painter.drawLine(self.crop_rect.left() + self.crop_rect.width() // 3, self.crop_rect.top(), self.crop_rect.left() + self.crop_rect.width() // 3, self.crop_rect.bottom())
            painter.drawLine(self.crop_rect.left() + 2 * self.crop_rect.width() // 3, self.crop_rect.top(), self.crop_rect.left() + 2 * self.crop_rect.width() // 3, self.crop_rect.bottom())

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 220))
            for handle in self.handles.values():
                painter.drawRect(handle)
