from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtCore import Qt, QPoint, QPointF, Signal
import numpy as np
from scipy.interpolate import CubicSpline

class CurveWidget(QWidget):
    curveChanged = Signal(np.ndarray)  # Emit 256-element LUT
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(256, 256)
        self.setMaximumSize(256, 256)
        self.setMouseTracking(True)
        
        # Control points: [(x, y), ...] normalized 0-1
        self.points = [(0.0, 0.0), (1.0, 1.0)]  # Start with linear
        self.selected_point = None
        self.dragging = False
        self.hover_point = None
        
        # Styling
        self.setStyleSheet("background: #18181b; border: 1px solid #3f3f46; border-radius: 4px;")
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # Draw grid
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        for i in range(1, 4):
            x = int(w * i / 4)
            y = int(h * i / 4)
            painter.drawLine(x, 0, x, h)
            painter.drawLine(0, y, w, y)
        
        # Draw diagonal reference line
        painter.setPen(QPen(QColor(80, 80, 80), 1, Qt.DashLine))
        painter.drawLine(0, h, w, 0)
        
        # Draw curve
        lut = self.get_curve_lut()
        painter.setPen(QPen(QColor(99, 102, 241), 2))  # Indigo
        for i in range(len(lut) - 1):
            x1 = int(i * w / 255)
            y1 = int(h - int(lut[i]) * h / 255)
            x2 = int((i + 1) * w / 255)
            y2 = int(h - int(lut[i + 1]) * h / 255)
            painter.drawLine(x1, y1, x2, y2)
        
        # Draw control points
        for i, (px, py) in enumerate(self.points):
            x = int(px * w)
            y = int(h - py * h)
            
            # Determine color
            if i == self.selected_point:
                color = QColor(239, 68, 68)  # Red when selected
            elif i == self.hover_point:
                color = QColor(244, 244, 245)  # White when hovering
            else:
                color = QColor(156, 163, 175)  # Gray
            
            # Draw point
            painter.setPen(QPen(QColor(30, 30, 30), 2))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPoint(x, y), 5, 5)
        
        painter.end()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            w, h = self.width(), self.height()
            click_x = event.pos().x() / w
            click_y = 1.0 - event.pos().y() / h
            
            # Check if clicking on existing point
            for i, (px, py) in enumerate(self.points):
                dist = ((click_x - px) ** 2 + (click_y - py) ** 2) ** 0.5
                if dist < 0.05:  # Within 5% distance
                    self.selected_point = i
                    self.dragging = True
                    return
            
            # Add new point (but not at endpoints)
            if 0.01 < click_x < 0.99:
                self.points.append((click_x, click_y))
                self.points.sort(key=lambda p: p[0])
                self.selected_point = self.points.index((click_x, click_y))
                self.dragging = True
                self.update()
                self.emit_curve()
        
        elif event.button() == Qt.RightButton:
            # Remove point (but not endpoints)
            w, h = self.width(), self.height()
            click_x = event.pos().x() / w
            click_y = 1.0 - event.pos().y() / h
            
            for i, (px, py) in enumerate(self.points):
                if i == 0 or i == len(self.points) - 1:
                    continue  # Can't remove endpoints
                dist = ((click_x - px) ** 2 + (click_y - py) ** 2) ** 0.5
                if dist < 0.05:
                    self.points.pop(i)
                    self.selected_point = None
                    self.update()
                    self.emit_curve()
                    return
    
    def mouseMoveEvent(self, event):
        w, h = self.width(), self.height()
        mouse_x = event.pos().x() / w
        mouse_y = 1.0 - event.pos().y() / h
        
        if self.dragging and self.selected_point is not None:
            # Move selected point
            px, py = self.points[self.selected_point]
            
            # Constrain x for non-endpoint points
            if self.selected_point == 0:
                new_x = 0.0
            elif self.selected_point == len(self.points) - 1:
                new_x = 1.0
            else:
                # Keep between neighbors
                prev_x = self.points[self.selected_point - 1][0]
                next_x = self.points[self.selected_point + 1][0]
                new_x = max(prev_x + 0.01, min(next_x - 0.01, mouse_x))
            
            # Constrain y
            new_y = max(0.0, min(1.0, mouse_y))
            
            self.points[self.selected_point] = (new_x, new_y)
            self.update()
            # Don't emit curve on every mouse move - only on release for better performance
            # self.emit_curve()
        else:
            # Update hover state
            old_hover = self.hover_point
            self.hover_point = None
            for i, (px, py) in enumerate(self.points):
                dist = ((mouse_x - px) ** 2 + (mouse_y - py) ** 2) ** 0.5
                if dist < 0.05:
                    self.hover_point = i
                    break
            
            if old_hover != self.hover_point:
                self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            # Emit curve after dragging is complete
            if self.selected_point is not None:
                self.emit_curve()
    
    def get_curve_lut(self):
        """Return 256-element lookup table using cubic spline"""
        if len(self.points) < 2:
            return np.arange(256, dtype=np.uint8)
        
        # Extract x and y
        xs = np.array([p[0] for p in self.points])
        ys = np.array([p[1] for p in self.points])
        
        # Create spline
        if len(self.points) == 2:
            # Linear interpolation for 2 points
            x_new = np.linspace(0, 1, 256)
            y_new = np.interp(x_new, xs, ys)
        else:
            # Cubic spline for 3+ points
            cs = CubicSpline(xs, ys, bc_type='clamped')
            x_new = np.linspace(0, 1, 256)
            y_new = cs(x_new)
        
        # Clamp and convert to 0-255
        y_new = np.clip(y_new, 0, 1)
        lut = np.clip((y_new * 255), 0, 255).astype(np.uint8)
        
        return lut
    
    def emit_curve(self):
        """Emit the curve changed signal"""
        lut = self.get_curve_lut()
        self.curveChanged.emit(lut)
    
    def reset_curve(self):
        """Reset to linear curve"""
        self.points = [(0.0, 0.0), (1.0, 1.0)]
        self.selected_point = None
        self.update()
        self.emit_curve()
    
    def set_curve_from_lut(self, lut):
        """Set curve from existing LUT (for loading saved curves)"""
        if lut is None or len(lut) != 256:
            self.reset_curve()
            return
        
        # Sample points from LUT
        # For simplicity, just use endpoints for now
        # A more sophisticated approach would detect inflection points
        self.points = [(0.0, lut[0] / 255.0), (1.0, lut[255] / 255.0)]
        self.update()
