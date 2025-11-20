# การสร้างไฟล์ติดตั้ง PhotoRaw สำหรับ macOS

## วิธีการ Build

### 1. ติดตั้ง Dependencies (ครั้งแรกเท่านั้น)
```bash
pip install py2app
```

### 2. Build แอป
```bash
./build_mac.sh
```

หรือ

```bash
python setup.py py2app
```

### 3. ติดตั้งแอป
หลังจาก build เสร็จ ไฟล์ `PhotoRaw.app` จะอยู่ในโฟลเดอร์ `dist/`

**วิธีติดตั้ง:**
1. เปิด Finder ไปที่โฟลเดอร์ `dist/`
2. ลาก `PhotoRaw.app` ไปวางในโฟลเดอร์ `Applications`
3. เสร็จแล้ว! เปิดใช้งานได้จาก Launchpad หรือ Applications

## หมายเหตุ

- ไฟล์ `.app` จะมีขนาดใหญ่เพราะรวม Python และ libraries ทั้งหมดไว้
- ครั้งแรกที่เปิดอาจมี warning จาก macOS (เพราะไม่ได้ sign) ให้:
  - คลิกขวาที่แอป → เลือก "Open"
  - หรือไปที่ System Preferences → Security & Privacy → คลิก "Open Anyway"

## การสร้าง DMG (Installer)

ถ้าต้องการสร้างไฟล์ติดตั้งแบบ `.dmg`:

```bash
hdiutil create -volname "PhotoRaw" -srcfolder dist/PhotoRaw.app -ov -format UDZO PhotoRaw.dmg
```

## Troubleshooting

ถ้า build ไม่สำเร็จ ลองทำตามนี้:

1. ลบโฟลเดอร์ build และ dist:
   ```bash
   rm -rf build dist
   ```

2. ติดตั้ง dependencies ใหม่:
   ```bash
   pip install --upgrade py2app PySide6 numpy pillow
   ```

3. Build อีกครั้ง
