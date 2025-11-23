# การสร้างไฟล์ติดตั้ง PhotoRaw สำหรับ macOS

## วิธีการ Build

### 1. ติดตั้ง Dependencies (ครั้งแรกเท่านั้น)
```bash
pip install pyinstaller
```

### 2. Build แอป
```bash
./build_mac.sh
```

หรือ

```bash
pyinstaller Ninlab.spec
```

### 3. ติดตั้งแอป
หลังจาก build เสร็จ ไฟล์ `Ninlab.app` จะอยู่ในโฟลเดอร์ `dist/`

**วิธีติดตั้ง:**
1. เปิด Finder ไปที่โฟลเดอร์ `dist/`
2. ลาก `Ninlab.app` ไปวางในโฟลเดอร์ `Applications`
3. เสร็จแล้ว! เปิดใช้งานได้จาก Launchpad หรือ Applications

## หมายเหตุ

- ไฟล์ `.app` จะมีขนาดใหญ่เพราะรวม Python และ libraries ทั้งหมดไว้
- ครั้งแรกที่เปิดอาจมี warning จาก macOS (เพราะไม่ได้ sign) ให้:
  - คลิกขวาที่แอป → เลือก "Open"
  - หรือไปที่ System Preferences → Security & Privacy → คลิก "Open Anyway"

## การสร้าง DMG (Installer)

ถ้าต้องการสร้างไฟล์ติดตั้งแบบ `.dmg`:

```bash
hdiutil create -volname "Ninlab" -srcfolder dist/Ninlab.app -ov -format UDZO Ninlab.dmg
```

## Troubleshooting

ถ้า build ไม่สำเร็จ ลองทำตามนี้:

1. ลบโฟลเดอร์ build และ dist:
   ```bash
   rm -rf build dist
   ```

2. ติดตั้ง dependencies ใหม่:
   ```bash
   pip install --upgrade pyinstaller PySide6 numpy pillow
   ```

3. Build อีกครั้ง
