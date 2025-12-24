"""
Histogram Widget for Ninlab
Displays RGB histogram similar to Lightroom style
"""
import numpy as np
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QPainterPath


class HistogramWidget(QWidget):
    """
    A widget that displays an RGB histogram similar to Lightroom.
    Shows separate histograms for R, G, B channels with transparency overlay.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 100)
        self.setMaximumHeight(130)
        
        # Histogram data (256 bins per channel)
        self.hist_r = np.zeros(256, dtype=np.float32)
        self.hist_g = np.zeros(256, dtype=np.float32)
        self.hist_b = np.zeros(256, dtype=np.float32)
        self.hist_luma = np.zeros(256, dtype=np.float32)
        
        # Display mode: 'rgb' or 'luma'
        self.mode = 'rgb'
        
        # Style
        self.bg_color = QColor("#18181b")
        self.grid_color = QColor("#3f3f46")
        
    def update_histogram(self, image_array):
        """
        Update histogram from image array.
        Args:
            image_array: numpy array of shape (H, W, 3) with values in range [0, 255]
        """
        if image_array is None or image_array.size == 0:
            self.hist_r = np.zeros(256, dtype=np.float32)
            self.hist_g = np.zeros(256, dtype=np.float32)
            self.hist_b = np.zeros(256, dtype=np.float32)
            self.hist_luma = np.zeros(256, dtype=np.float32)
            self.update()
            return
            
        # Ensure uint8
        if image_array.dtype != np.uint8:
            image_array = np.clip(image_array, 0, 255).astype(np.uint8)
        
        # Try using Rust for ultra-fast calculation
        try:
            import ninlab_core
            hist_r, hist_g, hist_b = ninlab_core.calculate_histogram(image_array)
            self.hist_r = hist_r.astype(np.float32)
            self.hist_g = hist_g.astype(np.float32)
            self.hist_b = hist_b.astype(np.float32)
        except (ImportError, AttributeError):
            # Fallback to NumPy (slower)
            self.hist_r, _ = np.histogram(image_array[:, :, 0], bins=256, range=(0, 256))
            self.hist_g, _ = np.histogram(image_array[:, :, 1], bins=256, range=(0, 256))
            self.hist_b, _ = np.histogram(image_array[:, :, 2], bins=256, range=(0, 256))
            self.hist_r = self.hist_r.astype(np.float32)
            self.hist_g = self.hist_g.astype(np.float32)
            self.hist_b = self.hist_b.astype(np.float32)
        
        # Calculate luminance histogram (weighted average)
        luma = (0.299 * image_array[:, :, 0] + 
                0.587 * image_array[:, :, 1] + 
                0.114 * image_array[:, :, 2]).astype(np.uint8)
        self.hist_luma, _ = np.histogram(luma, bins=256, range=(0, 256))
        self.hist_luma = self.hist_luma.astype(np.float32)
        
        # Normalize to 0-1 range (log scale for better visibility)
        max_val = max(self.hist_r.max(), self.hist_g.max(), self.hist_b.max())
        if max_val > 0:
            # Apply log scale for better dynamic range
            self.hist_r = np.log1p(self.hist_r) / np.log1p(max_val)
            self.hist_g = np.log1p(self.hist_g) / np.log1p(max_val)
            self.hist_b = np.log1p(self.hist_b) / np.log1p(max_val)
        
        max_luma = self.hist_luma.max()
        if max_luma > 0:
            self.hist_luma = np.log1p(self.hist_luma) / np.log1p(max_luma)
        
        self.update()
    
    def set_mode(self, mode):
        """Set display mode: 'rgb' or 'luma'"""
        self.mode = mode
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Draw background
        painter.fillRect(self.rect(), self.bg_color)
        
        # Draw grid (subtle)
        painter.setPen(QPen(self.grid_color, 1))
        for i in range(1, 4):
            y = h * i / 4
            painter.drawLine(0, int(y), w, int(y))
        
        # Draw histogram
        if self.mode == 'rgb':
            self._draw_rgb_histogram(painter, w, h)
        else:
            self._draw_luma_histogram(painter, w, h)
        
        # Draw border
        painter.setPen(QPen(QColor("#52525b"), 1))
        painter.drawRect(0, 0, w - 1, h - 1)
    
    def _draw_rgb_histogram(self, painter, w, h):
        """Draw RGB histogram with blended colors"""
        # Draw each channel with additive blending
        channels = [
            (self.hist_r, QColor(255, 0, 0, 100)),    # Red
            (self.hist_g, QColor(0, 255, 0, 100)),    # Green
            (self.hist_b, QColor(0, 0, 255, 100))     # Blue
        ]
        
        for hist, color in channels:
            path = QPainterPath()
            path.moveTo(0, h)
            
            for i in range(256):
                x = (i / 255.0) * (w - 1)
                y = h - (hist[i] * (h - 4))  # Leave 4px padding
                path.lineTo(x, max(0, y))
            
            path.lineTo(w, h)
            path.closeSubpath()
            
            # Fill with color
            painter.fillPath(path, color)
    
    def _draw_luma_histogram(self, painter, w, h):
        """Draw luminance histogram in white"""
        path = QPainterPath()
        path.moveTo(0, h)
        
        for i in range(256):
            x = (i / 255.0) * (w - 1)
            y = h - (self.hist_luma[i] * (h - 4))
            path.lineTo(x, max(0, y))
        
        path.lineTo(w, h)
        path.closeSubpath()
        
        # Fill with gradient from dark to light
        gradient = QLinearGradient(0, h, 0, 0)
        gradient.setColorAt(0, QColor(100, 100, 100, 100))
        gradient.setColorAt(1, QColor(200, 200, 200, 150))
        
        painter.fillPath(path, gradient)
        
        # Draw outline
        painter.setPen(QPen(QColor(200, 200, 200, 200), 1))
        painter.drawPath(path)
