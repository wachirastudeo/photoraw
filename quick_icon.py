"""
สร้าง icon.ico จาก logo.svg อย่างง่าย
ใช้ cairosvg ถ้ามี ถ้าไม่มีก็สร้างแบบง่ายด้วย PIL
"""
from PIL import Image, ImageDraw, ImageFont
import os

try:
    # ลองใช้ cairosvg ก่อน
    import cairosvg
    print("✅ Using cairosvg for high-quality SVG rendering")
    
    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    
    for size in sizes:
        # แปลง SVG เป็น PNG
        png_data = cairosvg.svg2png(
            url='logo.svg',
            output_width=size,
            output_height=size
        )
        
        # โหลดเป็น PIL Image
        from io import BytesIO
        img = Image.open(BytesIO(png_data))
        images.append(img)
        print(f"   ✓ Created {size}x{size}")
    
    # บันทึกเป็น ICO
    images[0].save(
        'icon.ico',
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print(f"\n✅ icon.ico created successfully with {len(sizes)} sizes!")
    
except ImportError:
    print("⚠️  cairosvg not found, creating simple gradient icon...")
    
    # สร้าง icon ง่ายๆด้วย gradient สวยๆ
    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    
    for size in sizes:
        # สร้างภาพพื้นฐาน
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # วงกลมพื้นหลัง (gradient แบบง่าย - น้ำเงิน)
        center = size // 2
        radius = int(size * 0.45)
        
        # วาดวงกลมหลัก
        draw.ellipse(
            [center-radius, center-radius, center+radius, center+radius],
            fill=(59, 130, 246, 255),  # สีน้ำเงิน
            outline=(139, 92, 246, 255),  # ขอบสีม่วง
            width=max(1, size // 40)
        )
        
        # วงกลมตรงกลาง (เหมือน aperture)
        inner_radius = int(radius * 0.4)
        draw.ellipse(
            [center-inner_radius, center-inner_radius, 
             center+inner_radius, center+inner_radius],
            fill=(96, 165, 250, 200),  # สีฟ้าอ่อน
        )
        
        # เส้นขอบในเพิ่มความสวย
        if size >= 32:
            line_radius = int(radius * 0.7)
            draw.ellipse(
                [center-line_radius, center-line_radius,
                 center+line_radius, center+line_radius],
                outline=(96, 165, 250, 150),
                width=max(1, size // 64)
            )
        
        images.append(img)
        print(f"   ✓ Created {size}x{size}")
    
    # บันทึกเป็น ICO
    images[0].save(
        'icon.ico',
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print(f"\n✅ icon.ico created successfully!")
    print("   💡 For best quality, install cairosvg: pip install cairosvg")

print("\n📝 Next steps:")
print("   1. Run: pyinstaller Ninlab.spec --noconfirm --clean")
print("   2. Run: dist\\NinlabApp\\NinlabApp.exe")
print("   3. Icon should now appear! 🎉")
