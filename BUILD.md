# 🚀 คู่มือ Build Ninlab

## ✅ ขั้นตอนที่ 1: ติดตั้ง Dependencies (ครั้งแรกเท่านั้น)

```bash
pip3 install pyinstaller maturin numpy PySide6 Pillow rawpy exifread scipy
```

## 🦀 ขั้นตอนที่ 2: Build Rust Extension (ครั้งแรกเท่านั้น)

```bash
cd ninlab_core_rs
python3 -m maturin develop --release
cd ..
```

## 📦 ขั้นตอนที่ 3: Build แอพ

```bash
pyinstaller Ninlab.spec --noconfirm
```

รอประมาณ 1-2 นาที แอพจะอยู่ที่ `dist/Ninlab.app`

---

## 🧪 ทดสอบแอพ

```bash
open dist/Ninlab.app
```

---

## 💾 สร้าง DMG Installer (สำหรับแจกจ่าย)

```bash
hdiutil create -volname "Ninlab" -srcfolder dist/Ninlab.app -ov -format UDZO Ninlab.dmg
```

---

## 🔧 Troubleshooting

### แอพปิดทันที
```bash
# ลบ build เก่า
rm -rf build dist

# Build ใหม่
pyinstaller Ninlab.spec --noconfirm
```

### macOS บล็อกแอพ
1. คลิกขวาที่ `Ninlab.app` → เลือก **"Open"**
2. หรือไปที่ **System Settings** → **Privacy & Security** → คลิก **"Open Anyway"**

---

## 🎯 คำสั่งรวด (Build ทั้งหมด)

```bash
# ติดตั้ง dependencies (ครั้งแรก)
pip3 install pyinstaller maturin numpy PySide6 Pillow rawpy exifread scipy

# Build Rust extension (ครั้งแรก)
cd ninlab_core_rs && python3 -m maturin develop --release && cd ..

# Build แอพ
pyinstaller Ninlab.spec --noconfirm

# เปิดทดสอบ
open dist/Ninlab.app
```

---

## 📝 หมายเหตุ

- แอพที่ Build จะมีขนาดใหญ่ (รวม Python และ libraries ทั้งหมด)
- ไม่ต้อง code sign ถ้าใช้เอง แต่ถ้าจะแจกต้อง sign
- ไฟล์ `.dmg` สะดวกสำหรับแจกจ่าย

---

**เสร็จแล้ว!** 🎉
