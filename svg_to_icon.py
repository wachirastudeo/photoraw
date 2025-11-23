"""
สคริปต์สำหรับแปลง SVG เป็นไอคอน Windows ที่คมชัดสูงสุด
ใช้ cairosvg หรือ svglib สำหรับการ render SVG คุณภาพสูง
"""

import os
import sys

def check_and_install_dependencies():
    """ตรวจสอบและติดตั้ง dependencies ที่จำเป็น"""
    try:
        import cairosvg
        print("✅ cairosvg is installed")
        return 'cairosvg'
    except ImportError:
        print("⚠️  cairosvg not found, trying svglib...")
        try:
            from svglib.svglib import svg2rlg
            from reportlab.graphics import renderPM
            print("✅ svglib is installed")
            return 'svglib'
        except ImportError:
            print("\n❌ Required libraries not found!")
            print("\nPlease install one of the following:")
            print("  Option 1 (Recommended): pip install cairosvg")
            print("  Option 2: pip install svglib reportlab")
            print("\nAfter installation, run this script again.")
            return None

def svg_to_png_cairosvg(svg_path, png_path, size):
    """แปลง SVG เป็น PNG ด้วย cairosvg (คุณภาพสูงสุด)"""
    import cairosvg
    cairosvg.svg2png(
        url=svg_path,
        write_to=png_path,
        output_width=size,
        output_height=size,
        background_color='transparent'
    )

def svg_to_png_svglib(svg_path, png_path, size):
    """แปลง SVG เป็น PNG ด้วย svglib"""
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    
    drawing = svg2rlg(svg_path)
    # Scale to desired size
    scale = size / max(drawing.width, drawing.height)
    drawing.width = size
    drawing.height = size
    drawing.scale(scale, scale)
    
    renderPM.drawToFile(drawing, png_path, fmt='PNG', bg=0xffffff)

def create_icon_from_svg(svg_path, output_ico_path):
    """สร้างไอคอน ICO จาก SVG"""
    from PIL import Image, ImageFilter, ImageEnhance
    
    print("=" * 60)
    print("🎨 SVG TO PIXEL-PERFECT ICON CONVERTER")
    print("=" * 60)
    print(f"\n📁 Source: {svg_path}")
    
    # ตรวจสอบ dependencies
    method = check_and_install_dependencies()
    if method is None:
        return False
    
    # ขนาดที่ต้องการสร้าง
    sizes = [256, 128, 64, 48, 32, 16]
    
    print(f"\n🔧 Creating {len(sizes)} icon sizes from SVG...")
    icon_images = []
    temp_files = []
    
    for size in sizes:
        print(f"\n   📐 Rendering {size}x{size} from SVG...")
        
        # สร้างไฟล์ PNG ชั่วคราว
        temp_png = f"temp_icon_{size}.png"
        temp_files.append(temp_png)
        
        try:
            # Render SVG เป็น PNG ด้วยขนาดที่ต้องการ
            if method == 'cairosvg':
                svg_to_png_cairosvg(svg_path, temp_png, size)
            else:
                svg_to_png_svglib(svg_path, temp_png, size)
            
            # โหลด PNG ที่สร้างขึ้น
            img = Image.open(temp_png)
            
            # แปลงเป็น RGBA ถ้ายังไม่ใช่
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # ปรับความคมชัดเล็กน้อยสำหรับขนาดเล็ก
            if size <= 48:
                print(f"      ✨ Enhancing sharpness for small size...")
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(1.3)
                # เพิ่ม contrast เล็กน้อย
                contrast = ImageEnhance.Contrast(img)
                img = contrast.enhance(1.1)
            
            icon_images.append(img)
            print(f"      ✅ Done!")
            
        except Exception as e:
            print(f"      ❌ Error rendering {size}x{size}: {e}")
            return False
    
    # บันทึกเป็นไฟล์ ICO
    print(f"\n💾 Saving to {output_ico_path}...")
    sizes_tuple = [(s, s) for s in sizes]
    
    icon_images[0].save(
        output_ico_path,
        format='ICO',
        sizes=sizes_tuple,
        append_images=icon_images[1:]
    )
    
    # ลบไฟล์ชั่วคราว
    print(f"\n🧹 Cleaning up temporary files...")
    for temp_file in temp_files:
        try:
            os.remove(temp_file)
        except:
            pass
    
    # ตรวจสอบผลลัพธ์
    file_size = os.path.getsize(output_ico_path)
    print(f"\n✅ SUCCESS!")
    print(f"   Output: {output_ico_path}")
    print(f"   File size: {file_size:,} bytes")
    print(f"   Resolutions: {', '.join([f'{s}x{s}' for s in sizes])}")
    
    return True

def create_wizard_images_from_svg(svg_path):
    """สร้างภาพสำหรับ Inno Setup installer จาก SVG"""
    from PIL import Image, ImageEnhance
    
    print(f"\n📦 Creating installer wizard images from SVG...")
    
    method = check_and_install_dependencies()
    if method is None:
        return False
    
    # Large wizard: 164x314 (ใช้ไอคอน 128x128)
    temp_large = "temp_wizard_large.png"
    
    if method == 'cairosvg':
        svg_to_png_cairosvg(svg_path, temp_large, 128)
    else:
        svg_to_png_svglib(svg_path, temp_large, 128)
    
    icon_large = Image.open(temp_large)
    if icon_large.mode != 'RGBA':
        icon_large = icon_large.convert('RGBA')
    
    # เพิ่มความคมชัด
    enhancer = ImageEnhance.Sharpness(icon_large)
    icon_large = enhancer.enhance(1.2)
    
    # สร้างพื้นหลังสีขาว
    large_bg = Image.new('RGB', (164, 314), (255, 255, 255))
    
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
    os.remove(temp_large)
    print(f"   ✅ wizard_large.bmp (164x314)")
    
    # Small wizard: 55x55 (ใช้ไอคอน 48x48)
    temp_small = "temp_wizard_small.png"
    
    if method == 'cairosvg':
        svg_to_png_cairosvg(svg_path, temp_small, 48)
    else:
        svg_to_png_svglib(svg_path, temp_small, 48)
    
    icon_small = Image.open(temp_small)
    if icon_small.mode != 'RGBA':
        icon_small = icon_small.convert('RGBA')
    
    # เพิ่มความคมชัด
    enhancer = ImageEnhance.Sharpness(icon_small)
    icon_small = enhancer.enhance(1.3)
    
    # สร้างพื้นหลังสีขาว
    small_bg = Image.new('RGB', (55, 55), (255, 255, 255))
    
    # แปลง RGBA เป็น RGB
    if icon_small.mode == 'RGBA':
        bg = Image.new('RGB', icon_small.size, (255, 255, 255))
        bg.paste(icon_small, mask=icon_small.split()[3])
        icon_small = bg
    
    x = (55 - 48) // 2
    y = (55 - 48) // 2
    small_bg.paste(icon_small, (x, y))
    small_bg.save("wizard_small.bmp")
    os.remove(temp_small)
    print(f"   ✅ wizard_small.bmp (55x55)")
    
    return True

if __name__ == "__main__":
    try:
        source_svg = "icon.svg"
        output_ico = "icon.ico"
        
        # ตรวจสอบว่ามีไฟล์ SVG หรือไม่
        if not os.path.exists(source_svg):
            print(f"❌ Error: {source_svg} not found!")
            exit(1)
        
        # สร้างไอคอนจาก SVG
        success = create_icon_from_svg(source_svg, output_ico)
        
        if success:
            # สร้าง wizard images
            create_wizard_images_from_svg(source_svg)
            
            print("\n" + "=" * 60)
            print("🎉 ALL DONE!")
            print("=" * 60)
            print("\n📋 Next steps:")
            print("   1. Run: python -m PyInstaller Ninlab.spec")
            print("   2. Run: .\\build_installer.bat")
            print("\n💡 The icon should now be CRYSTAL CLEAR!")
            print("   SVG provides the best quality for all icon sizes.")
            print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
