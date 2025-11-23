from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QHBoxLayout, QSpinBox, QCheckBox, QLineEdit, QDialogButtonBox

class ExportOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Export Options")
        lay=QVBoxLayout(self); form=QFormLayout()

        self.cmb_fmt=QComboBox(); self.cmb_fmt.addItems(["JPEG","PNG"]); form.addRow("Format", self.cmb_fmt)
        rowQ=QHBoxLayout(); self.sp_quality=QSpinBox(); self.sp_quality.setRange(1,100); self.sp_quality.setValue(92)
        self.chk_prog=QCheckBox("Progressive"); self.chk_prog.setChecked(True)
        self.chk_opt=QCheckBox("Optimize"); self.chk_opt.setChecked(True)
        rowQ.addWidget(self.sp_quality); rowQ.addWidget(self.chk_prog); rowQ.addWidget(self.chk_opt)
        form.addRow("JPEG Quality", rowQ)

        rowL=QHBoxLayout(); self.cmb_long=QComboBox()
        self.cmb_long.addItems(["No resize","1200","1600","2048","3840","Custom"])
        self.sp_long=QSpinBox(); self.sp_long.setRange(320,20000); self.sp_long.setValue(2048); self.sp_long.setEnabled(False)
        rowL.addWidget(self.cmb_long); rowL.addWidget(self.sp_long); form.addRow("Long Edge", rowL)

        # File Naming
        self.cmb_naming = QComboBox()
        self.cmb_naming.addItems(["Original Name", "Custom Name + Sequence"])
        form.addRow("File Naming", self.cmb_naming)

        self.row_custom_name = QHBoxLayout()
        self.ed_custom_text = QLineEdit("Photo"); self.ed_custom_text.setPlaceholderText("Custom Text")
        self.sp_start_num = QSpinBox(); self.sp_start_num.setRange(1, 999999); self.sp_start_num.setValue(1)
        self.sp_start_num.setPrefix("Start: ")
        self.row_custom_name.addWidget(self.ed_custom_text)
        self.row_custom_name.addWidget(self.sp_start_num)
        
        # Container widget for custom name row to easily hide/show
        self.wid_custom_name = QDialog() # Dummy widget to hold layout? No, just toggle visibility of widgets or add to a frame
        # Better: Add row but keep reference to widgets to enable/disable or hide
        # Let's just add the layout to form and we will toggle visibility of items? 
        # QFormLayout doesn't make it easy to hide rows. Let's just add it and toggle visibility.
        # Actually, let's put it in a widget.
        from PySide6.QtWidgets import QWidget
        self.wid_custom_name = QWidget()
        self.wid_custom_name.setLayout(self.row_custom_name)
        form.addRow(" ", self.wid_custom_name) # Label space

        self.ed_suffix=QLineEdit("_edit"); form.addRow("Suffix", self.ed_suffix)

        # File Size Limit
        rowLimit = QHBoxLayout()
        self.chk_limit_size = QCheckBox("Limit File Size To")
        self.sp_limit_size = QSpinBox(); self.sp_limit_size.setRange(10, 50000); self.sp_limit_size.setValue(500); self.sp_limit_size.setSuffix(" KB")
        self.sp_limit_size.setEnabled(False)
        rowLimit.addWidget(self.chk_limit_size)
        rowLimit.addWidget(self.sp_limit_size)
        form.addRow("File Size", rowLimit)

        lay.addLayout(form)

        def on_fmt():
            isjpg=self.cmb_fmt.currentText()=="JPEG"
            self.sp_quality.setEnabled(isjpg); self.chk_prog.setEnabled(isjpg); self.chk_opt.setEnabled(isjpg)
            self.chk_limit_size.setEnabled(isjpg)
            self.sp_limit_size.setEnabled(isjpg and self.chk_limit_size.isChecked())

        def on_naming():
            iscustom = self.cmb_naming.currentText() == "Custom Name + Sequence"
            self.wid_custom_name.setVisible(iscustom)
            self.ed_suffix.setEnabled(not iscustom) # Disable suffix if custom naming? Or keep it? Usually custom naming replaces suffix.
            # Let's disable suffix for custom naming to avoid confusion "Photo-001_edit.jpg" vs "Photo-001.jpg"
            if iscustom: self.ed_suffix.setText("") 
            else: 
                if not self.ed_suffix.text(): self.ed_suffix.setText("_edit")

        self.cmb_fmt.currentTextChanged.connect(lambda _: on_fmt())
        self.chk_limit_size.toggled.connect(lambda _: on_fmt())
        self.cmb_naming.currentTextChanged.connect(lambda _: on_naming())
        self.cmb_long.currentTextChanged.connect(lambda _: self.sp_long.setEnabled(self.cmb_long.currentText()=="Custom"))
        
        on_fmt()
        on_naming()

        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); lay.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

    def get_options(self):
        fmt=self.cmb_fmt.currentText(); sel=self.cmb_long.currentText()
        long_edge=None if sel=="No resize" else (int(self.sp_long.value()) if sel=="Custom" else int(sel))
        
        naming_mode = self.cmb_naming.currentText()
        custom_text = self.ed_custom_text.text().strip()
        start_num = self.sp_start_num.value()
        
        limit_size_kb = self.sp_limit_size.value() if (self.chk_limit_size.isChecked() and fmt=="JPEG") else 0

        return {
            "fmt":fmt,"quality":int(self.sp_quality.value()),
            "progressive":bool(self.chk_prog.isChecked()),"optimize":bool(self.chk_opt.isChecked()),
            "long_edge":long_edge,"suffix":self.ed_suffix.text().strip(),
            "naming_mode": naming_mode, "custom_text": custom_text, "start_num": start_num,
            "limit_size_kb": limit_size_kb
        }
