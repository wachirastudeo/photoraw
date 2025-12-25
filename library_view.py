from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView, QWidget, QVBoxLayout, QFrame, QHBoxLayout
from PySide6.QtGui import QIcon, QPixmap

class LibraryView(QWidget):
    # Signal emitted when user double clicks an item to edit
    sig_open_edit = Signal(int) 
    # Signal emitted when rating changes (item_index, star_status)
    sig_rating_changed = Signal(int, bool)
    # Signal emitted when check state changes (item_name, is_checked)
    sig_check_changed = Signal(str, bool)
    # Signal emitted for bulk updates (is_checked_all)
    sig_bulk_check_changed = Signal(bool)
    # Signals for Copy/Paste Settings
    sig_copy_settings = Signal()
    sig_paste_settings = Signal()

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
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        # Defer stylesheet setting until we have paths
        # self.grid.installEventFilter(self)
        pass # Placeholder for layout order, actual style set below
        
        self.grid.installEventFilter(self)
        self.grid.itemDoubleClicked.connect(self._on_double_click)
        self.grid.itemChanged.connect(self._on_item_changed)
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._show_context_menu)
        
        # --- Generate Checkbox Icons for Styling ---
        import os
        from PySide6.QtGui import QPainter, QPen, QColor, QImage, QPainterPath
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path_checked = os.path.join(base_dir, "cb_checked.png")
        path_unchecked = os.path.join(base_dir, "cb_unchecked.png")
        
        if not os.path.exists(path_checked) or not os.path.exists(path_unchecked):
            # Draw Unchecked
            img = QImage(24, 24, QImage.Format_ARGB32)
            img.fill(Qt.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor("#a1a1aa"), 2))
            p.drawRoundedRect(2, 2, 20, 20, 4, 4)
            p.end()
            img.save(path_unchecked)
            
            # Draw Checked
            img.fill(Qt.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            # Box
            p.setPen(QPen(QColor("#4f46e5"), 2)) # Indigo outline
            p.setBrush(QColor("#4f46e5"))       # Indigo fill
            p.drawRoundedRect(2, 2, 20, 20, 4, 4)
            
            # Tick (White, Thick)
            p.setPen(QPen(QColor("white"), 3))
            p.setBrush(Qt.NoBrush)
            # Draw Tick: (6, 12) -> (10, 16) -> (18, 6)
            path = QPainterPath()
            path.moveTo(7, 12)
            path.lineTo(10, 16)
            path.lineTo(17, 7)
            p.drawPath(path)
            p.end()
            img.save(path_checked)

        # Normalize paths for CSS
        url_checked = path_checked.replace("\\", "/")
        url_unchecked = path_unchecked.replace("\\", "/")

        self.grid.setStyleSheet(f"""
            QListWidget {{
                background: #18181b;
                border: none;
                padding: 20px;
            }}
            QListWidget::item {{
                background: #27272a;
                border-radius: 6px;
                padding: 10px;
                color: #e4e4e7;
            }}
            QListWidget::item:selected {{
                background: #4f46e5;
                color: white;
            }}
            QListWidget::item:hover:!selected {{
                background: #3f3f46;
            }}
            QListWidget::indicator {{
                width: 24px;
                height: 24px;
            }}
            QListWidget::indicator:unchecked {{
                image: url({url_unchecked});
            }}
            QListWidget::indicator:checked {{
                image: url({url_checked});
            }}
        """)
        
        layout.addWidget(self.grid)

    def add_item(self, name, pixmap, starred=False):
        import os
        display_name = os.path.basename(name)
        it = QListWidgetItem(display_name)
        it.setIcon(QIcon(pixmap))
        it.setData(Qt.UserRole, name)
        
        # Enable Checkbox
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked) # Default to Checked as per requirement

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
        import datetime
        print(f"🖱️ LibraryView Double Click detected at {datetime.datetime.now()}!")
        row = self.grid.row(item)
        print(f"   -> Emitting sig_open_edit for row {row}")
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

    def _toggle_check_selected(self):
        for item in self.grid.selectedItems():
            current = item.checkState()
            new_state = Qt.Unchecked if current == Qt.Checked else Qt.Checked
            item.setCheckState(new_state)

    def _show_context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self.grid)
        
        act_star = menu.addAction("Toggle Star (1)")
        act_star.triggered.connect(self._toggle_star_selected)

        act_check = menu.addAction("Toggle Check")
        act_check.triggered.connect(self._toggle_check_selected)
        
        menu.addSeparator()
        
        act_copy = menu.addAction("Copy Settings")
        act_copy.triggered.connect(self.sig_copy_settings.emit)
        
        act_paste = menu.addAction("Paste Settings")
        act_paste.triggered.connect(self.sig_paste_settings.emit)
        
        menu.addSeparator()
        
        act_edit = menu.addAction("Open in Develop")
        act_edit.triggered.connect(lambda: self.sig_open_edit.emit(self.grid.currentRow()))
        
        menu.exec(self.grid.mapToGlobal(pos))

    def set_all_checked(self, checked=True):
        state = Qt.Checked if checked else Qt.Unchecked
        self.grid.blockSignals(True) # Block signals to prevent massive rebuilds
        for i in range(self.grid.count()):
            self.grid.item(i).setCheckState(state)
        self.grid.blockSignals(False)
        
        # Manually trigger ONE update for the bulk change (Optional: Main app needs to know)
        # Emitting for every item is too slow.
        # Ideally, emit a "bulk_changed" signal, or just rely on the user to interact or save?
        # Requirement: "If unchecked, not show in Develop" -> Requires sync.
        # So we MUST sync `self.items`.
        # I'll iterate and emit? Or add a bulk signal? 
        # Making a bulk signal is better.
        # But for quick fix, let's just make `Main` have a `refresh_all_checks` or similar.
        # OR: emit one signal "ALL_CHANGED"?
        # Simplified approach: Use blocked signals, but then how to sync?
        # Answer: Iterate and sync to Main directly? No, decoupling.
        # Let's emit a special signal `sig_bulk_check_changed`?
        # Or, just iterate and emit individually? No, that defeats the purpose of blocking.
        # Actually, `blockSignals` blocks `itemChanged`.
        # If I unblock, `itemChanged` does NOT fire retrospectively.
        # So I need to manually handle the logic.
        
        # Better: iterate and emit `sig_check_changed` manually? 
        # Collecting all names and states and emitting one big list?
        # Let's keep it simple: 
        # Don't block signals? 
        # If 1000 items, 1000 emits -> 1000 `rebuild_filmstrip()` -> Freeze.
        
        # Solution: Add `sig_bulk_check`
        items_state = []
        for i in range(self.grid.count()):
             item = self.grid.item(i)
             items_state.append((item.data(Qt.UserRole), checked))
        
        # We need a new signal for this.
        self.sig_bulk_check_changed.emit(checked) 

    # Need to define the signal at class level first. I'll add it in next step.
    def get_checked_items(self):
        """Returns a list of rows that are checked."""
        checked_rows = []
        for i in range(self.grid.count()):
            item = self.grid.item(i)
            if item.checkState() == Qt.Checked:
                checked_rows.append(i)
        return checked_rows


    def _on_item_changed(self, item):
        # row = self.grid.row(item) # Unreliable if sorted or filtered
        name = item.data(Qt.UserRole)
        checked = (item.checkState() == Qt.Checked)
        self.sig_check_changed.emit(name, checked)
