from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView, QWidget, QVBoxLayout, QFrame
from PySide6.QtGui import QIcon, QPixmap

class LibraryView(QWidget):
    # Signal emitted when user double clicks an item to edit
    sig_open_edit = Signal(int) 
    # Signal emitted when rating changes (item_index, star_status)
    sig_rating_changed = Signal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setSpacing(10)
        self.grid.setIconSize(QSize(256, 190)) # Aspect ~4:3
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grid.setStyleSheet("""
            QListWidget {
                background: #18181b;
                border: none;
                padding: 20px;
            }
            QListWidget::item {
                background: #27272a;
                border-radius: 6px;
                padding: 10px;
                color: #e4e4e7;
            }
            QListWidget::item:selected {
                background: #4f46e5;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background: #3f3f46;
            }
        """)
        
        self.grid.installEventFilter(self)
        self.grid.itemDoubleClicked.connect(self._on_double_click)
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.grid)

    def add_item(self, name, pixmap, starred=False):
        import os
        display_name = os.path.basename(name)
        it = QListWidgetItem(display_name)
        it.setIcon(QIcon(pixmap))
        it.setData(Qt.UserRole, name)
        # Store metadata if needed, for now just index sync via row
        if starred:
            it.setText(f"{display_name} ★")
        self.grid.addItem(it)

    def update_item(self, index, pixmap=None, starred=None, name=None):
        if index < 0 or index >= self.grid.count(): return
        it = self.grid.item(index)
        if pixmap:
            it.setIcon(QIcon(pixmap))
        if starred is not None and name is not None:
             import os
             display_name = os.path.basename(name)
             it.setText(f"{display_name} {'★' if starred else ''}")

    def clear(self):
        self.grid.clear()

    def set_selection(self, index):
        if index < 0 or index >= self.grid.count(): return
        self.grid.setCurrentRow(index)

    def _on_double_click(self, item):
        row = self.grid.row(item)
        self.sig_open_edit.emit(row)
        
    def eventFilter(self, source, event):
        from PySide6.QtCore import QEvent
        if source == self.grid and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_1:
                self._toggle_star_selected()
                return True
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self.grid.currentRow() >= 0:
                    self.sig_open_edit.emit(self.grid.currentRow())
                return True
        return super().eventFilter(source, event)

    def _toggle_star_selected(self):
        for item in self.grid.selectedItems():
            row = self.grid.row(item)
            self.sig_rating_changed.emit(row, True) # True = toggle/set star
            
    def _show_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self.grid)
        
        act_star = menu.addAction("Toggle Star (1)")
        act_star.triggered.connect(self._toggle_star_selected)
        
        act_edit = menu.addAction("Open in Develop")
        act_edit.triggered.connect(lambda: self.sig_open_edit.emit(self.grid.currentRow()))
        
        menu.exec(self.grid.mapToGlobal(pos))
