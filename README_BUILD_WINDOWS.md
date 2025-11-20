# การสร้างไฟล์ติดตั้ง Ninlab สำหรับ Windows

## ข้อกำหนดเบื้องต้น

1. **Python 3.8+** ติดตั้งแล้วบนเครื่อง
2. **Dependencies ทั้งหมด** ติดตั้งแล้ว (PySide6, numpy, Pillow, rawpy)

## วิธีการ 1: สร้าง EXE ด้วย PyInstaller (แนะนำ)

### 1. ติดตั้ง PyInstaller (ครั้งแรกเท่านั้น)
```powershell
pip install pyinstaller
```

### 2. Build แอปพลิเคชัน
```powershell
.\build_windows.bat
```

หรือใช้คำสั่งโดยตรง:
```powershell
pyinstaller Ninlab.spec
```

### 3. ผลลัพธ์
หลังจาก build เสร็จ ไฟล์จะอยู่ในโฟลเดอร์ `dist\Ninlab\`
- `Ninlab.exe` - ไฟล์โปรแกรมหลัก
- DLL และไฟล์ที่จำเป็นอื่นๆ

**วิธีใช้งาน:**
- คัดลอกทั้งโฟลเดอร์ `dist\Ninlab\` ไปยังที่ที่ต้องการ
- เปิดโปรแกรมโดยดับเบิลคลิก `Ninlab.exe`

## วิธีการ 2: สร้าง Installer ด้วย Inno Setup (สำหรับแจกจ่าย)

### 1. ติดตั้ง Inno Setup
ดาวน์โหลดและติดตั้งจาก: https://jrsoftware.org/isdl.php

### 2. Build EXE ก่อน (ตามวิธีการ 1)
```powershell
.\build_windows.bat
```

### 3. สร้าง Installer
```powershell
.\build_installer.bat
```

หรือเปิด Inno Setup Compiler และ compile ไฟล์ `ninlab_installer.iss`

### 4. ผลลัพธ์
ไฟล์ติดตั้ง `NinlabSetup.exe` จะอยู่ในโฟลเดอร์ `installer_output\`

**คุณสมบัติของ Installer:**
- ติดตั้งโปรแกรมไปยัง Program Files
- สร้าง Desktop Shortcut
- สร้างรายการใน Start Menu
- มีตัวเลือก Uninstall

## วิธีการ 3: สร้าง Single EXE File (ไฟล์เดียว)

ถ้าต้องการไฟล์ `.exe` เดียว (ไม่ต้องมีโฟลเดอร์):

```powershell
pyinstaller --onefile --windowed --icon=icon.ico --name=Ninlab ^
  --add-data "icon.ico;." ^
  --hidden-import=imaging --hidden-import=workers ^
  --hidden-import=ui_helpers --hidden-import=catalog ^
  --hidden-import=export_dialog --hidden-import=cropper ^
  main.py
```

**หมายเหตุ:** ไฟล์เดียวจะใช้เวลาเปิดนานกว่าเล็กน้อย เพราะต้อง extract ไฟล์ก่อน

## Troubleshooting

### ปัญหา: Build ไม่สำเร็จ
```powershell
# ลบโฟลเดอร์ build และ dist
Remove-Item -Recurse -Force build, dist

# ติดตั้ง dependencies ใหม่
pip install --upgrade pyinstaller PySide6 numpy pillow rawpy

# Build อีกครั้ง
.\build_windows.bat
```

### ปัญหา: โปรแกรมเปิดไม่ได้หรือ Error
- ตรวจสอบว่าไฟล์ `icon.ico` อยู่ในโฟลเดอร์เดียวกับ `main.py`
- ตรวจสอบว่า Python modules ทั้งหมดติดตั้งครบ
- ลองรันด้วย console mode เพื่อดู error: เปลี่ยน `console=False` เป็น `console=True` ใน `Ninlab.spec`

### ปัญหา: ขนาดไฟล์ใหญ่เกินไป
- ใช้ UPX compression (เปิดอยู่แล้วใน spec file)
- ลบ modules ที่ไม่จำเป็นออก

## การแจกจ่าย

### สำหรับผู้ใช้ทั่วไป
แนะนำให้ใช้ **Inno Setup Installer** (`NinlabSetup.exe`) เพราะ:
- ติดตั้งง่าย คลิกเดียว
- มี Uninstaller
- สร้าง shortcuts อัตโนมัติ
- ดูมืออาชีพ

### สำหรับ Portable Version
ให้แจกจ่ายโฟลเดอร์ `dist\Ninlab\` ทั้งหมดในรูปแบบ ZIP:
```powershell
Compress-Archive -Path dist\Ninlab -DestinationPath Ninlab_Portable.zip
```

## ข้อมูลเพิ่มเติม

- **ขนาดไฟล์:** ประมาณ 150-300 MB (รวม Python runtime และ libraries)
- **ระบบปฏิบัติการ:** Windows 10/11 (64-bit)
- **การอัปเดต:** สร้าง installer ใหม่ทุกครั้งที่มีการเปลี่ยนแปลงโค้ด

## เวอร์ชัน

เปลี่ยนเวอร์ชันได้ที่:
- `Ninlab.spec` (สำหรับ PyInstaller)
- `ninlab_installer.iss` (สำหรับ Inno Setup)
- `setup.py` (ถ้าใช้)
