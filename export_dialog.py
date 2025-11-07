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

        self.ed_suffix=QLineEdit("_edit"); form.addRow("Suffix", self.ed_suffix)
        lay.addLayout(form)

        def on_fmt():
            isjpg=self.cmb_fmt.currentText()=="JPEG"
            self.sp_quality.setEnabled(isjpg); self.chk_prog.setEnabled(isjpg); self.chk_opt.setEnabled(isjpg)
        self.cmb_fmt.currentTextChanged.connect(lambda _: on_fmt()); on_fmt()
        self.cmb_long.currentTextChanged.connect(lambda _: self.sp_long.setEnabled(self.cmb_long.currentText()=="Custom"))

        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); lay.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

    def get_options(self):
        fmt=self.cmb_fmt.currentText(); sel=self.cmb_long.currentText()
        long_edge=None if sel=="No resize" else (int(self.sp_long.value()) if sel=="Custom" else int(sel))
        return {
            "fmt":fmt,"quality":int(self.sp_quality.value()),
            "progressive":bool(self.chk_prog.isChecked()),"optimize":bool(self.chk_opt.isChecked()),
            "long_edge":long_edge,"suffix":self.ed_suffix.text().strip() or "_edit"
        }
