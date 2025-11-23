"""
สคริปต์สำหรับสร้างไอคอน Windows ที่คมชัดสูงสุด
รองรับการสร้างจากไฟล์ PNG ขนาดใหญ่

วิธีใช้:
1. เตรียมไฟล์ icon.png ขนาดอย่างน้อย 512x512 หรือ 1024x1024 พิกเซล
2. รันสคริปต์นี้: python create_perfect_icon.py
3. Rebuild แอปพลิเคชัน

หมายเหตุ: ถ้ามีไฟล์ SVG จะได้ผลลัพธ์ที่ดีที่สุด
"""

from PIL import Image, ImageFilter, ImageEnhance, ImageDraw
import os

def create_pixel_perfect_icon(source_path, output_ico_path):
    """
    สร้างไอคอน ICO ที่คมชัดสูงสุดจากไฟล์ PNG
    """
    print("=" * 60)
    print("🎨 PIXEL-PERFECT ICON CREATOR")
    print("=" * 60)
    
    # โหลดภาพต้นฉบับ
    img = Image.open(source_path)
    print(f"\n📁 Source: {source_path}")
    print(f"   Size: {img.size[0]}x{img.size[1]} pixels")
    print(f"   Mode: {img.mode}")
    
    # ตรวจสอบขนาด
    if min(img.size) < 256:
        print(f"\n⚠️  WARNING: Source image is smaller than 256x256!")
        print(f"   Recommended: At least 512x512 or 1024x1024 pixels")
        print(f"   Current size may result in blurry icons.")
    
    # แปลงเป็น RGBA
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # ขนาดที่ต้องการสร้าง (เรียงจากใหญ่ไปเล็ก)
    sizes = [256, 128, 64, 48, 32, 16]
    
    print(f"\n🔧 Creating {len(sizes)} icon sizes...")
    icon_images = []
    
    for size in sizes:
        print(f"\n   📐 Creating {size}x{size} icon...")
        
        # ถ้าภาพต้นฉบับเล็กกว่าขนาดที่ต้องการ ให้ใช้ขนาดเดิม
        if min(img.size) < size:
            resized = img.resize((size, size), Image.Resampling.LANCZOS)
        else:
            # ใช้ LANCZOS สำหรับการ downsample คุณภาพสูง
            resized = img.resize((size, size), Image.Resampling.LANCZOS)
        
        # ปรับความคมชัดตามขนาด
        if size <= 48:
            # ขนาดเล็ก: ต้องการความคมชัดสูงมาก
            print(f"      ✨ Applying strong sharpening...")
            enhancer = ImageEnhance.Sharpness(resized)
            resized = enhancer.enhance(2.2)
            # ใช้ Unsharp Mask
            resized = resized.filter(ImageFilter.UnsharpMask(radius=0.8, percent=180, threshold=2))
            
        elif size <= 128:
            # ขนาดกลาง: ความคมชัดปานกลาง
            print(f"      ✨ Applying medium sharpening...")
            enhancer = ImageEnhance.Sharpness(resized)
            resized = enhancer.enhance(1.8)
            resized = resized.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        else:
            # ขนาดใหญ่: ความคมชัดเล็กน้อย
            print(f"      ✨ Applying light sharpening...")
            enhancer = ImageEnhance.Sharpness(resized)
            resized = enhancer.enhance(1.3)
        
        # เพิ่ม contrast เล็กน้อยเพื่อให้ดูคมชัดขึ้น
        contrast = ImageEnhance.Contrast(resized)
        resized = contrast.enhance(1.1)
        
        icon_images.append(resized)
        print(f"      ✅ Done!")
    
    # บันทึกเป็นไฟล์ ICO
    print(f"\n💾 Saving to {output_ico_path}...")
    sizes_tuple = [(s, s) for s in sizes]
    
    icon_images[0].save(
        output_ico_path,
        format='ICO',
        sizes=sizes_tuple,
        append_images=icon_images[1:]
    )
    
    # ตรวจสอบผลลัพธ์
    file_size = os.path.getsize(output_ico_path)
    print(f"\n✅ SUCCESS!")
    print(f"   Output: {output_ico_path}")
    print(f"   File size: {file_size:,} bytes")
    print(f"   Resolutions: {', '.join([f'{s}x{s}' for s in sizes])}")
    
    return True

def create_wizard_images(source_path):
    """
    สร้างภาพสำหรับ Inno Setup installer
    """
    print(f"\n📦 Creating installer wizard images...")
    
    img = Image.open(source_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Large wizard: 164x314
    large_bg = Image.new('RGB', (164, 314), (255, 255, 255))
    icon_large = img.resize((128, 128), Image.Resampling.LANCZOS)
    
    # เพิ่มความคมชัด
    enhancer = ImageEnhance.Sharpness(icon_large)
    icon_large = enhancer.enhance(1.6)
    
    # แปลง RGBA เป็น RGB
    if icon_large.mode == 'RGBA':
        bg = Image.new('RGB', icon_large.size, (255, 255, 255))
        bg.paste(icon_large, mask=icon_large.split()[3])
        icon_large = bg
    
    # วางตรงกลาง
    x = (164 - 128) // 2
    y = (314 - 128) // 2
    large_bg.paste(icon_large, (x, y))
    large_bg.save("wizard_large.bmp")
    print(f"   ✅ wizard_large.bmp (164x314)")
    
    # Small wizard: 55x55
    small_bg = Image.new('RGB', (55, 55), (255, 255, 255))
    icon_small = img.resize((48, 48), Image.Resampling.LANCZOS)
    
    # เพิ่มความคมชัดสูง
    enhancer = ImageEnhance.Sharpness(icon_small)
    icon_small = enhancer.enhance(2.2)
    icon_small = icon_small.filter(ImageFilter.UnsharpMask(radius=0.8, percent=180, threshold=2))
    
    # แปลง RGBA เป็น RGB
    if icon_small.mode == 'RGBA':
        bg = Image.new('RGB', icon_small.size, (255, 255, 255))
        bg.paste(icon_small, mask=icon_small.split()[3])
        icon_small = bg
    
    x = (55 - 48) // 2
    y = (55 - 48) // 2
    small_bg.paste(icon_small, (x, y))
    small_bg.save("wizard_small.bmp")
    print(f"   ✅ wizard_small.bmp (55x55)")

if __name__ == "__main__":
    try:
        source_png = "icon.png"
        output_ico = "icon.ico"
        
        # ตรวจสอบว่ามีไฟล์ต้นฉบับหรือไม่
        if not os.path.exists(source_png):
            print(f"❌ Error: {source_png} not found!")
            print(f"\n💡 Please provide:")
            print(f"   - PNG file: At least 512x512 or 1024x1024 pixels")
            print(f"   - Format: RGBA (with transparency)")
            print(f"   - Quality: Sharp, high-quality image")
            exit(1)
        
        # สร้างไอคอน
        create_pixel_perfect_icon(source_png, output_ico)
        
        # สร้าง wizard images
        create_wizard_images(source_png)
        
        print("\n" + "=" * 60)
        print("🎉 ALL DONE!")
        print("=" * 60)
        print("\n📋 Next steps:")
        print("   1. Run: python -m PyInstaller Ninlab.spec")
        print("   2. Run: .\\build_installer.bat")
        print("\n💡 Tips for best results:")
        print("   • Use source PNG at least 512x512 or 1024x1024 pixels")
        print("   • Make sure the source image is sharp and clear")
        print("   • After installing, clear Windows icon cache:")
        print("     ie4uinit.exe -show")
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
