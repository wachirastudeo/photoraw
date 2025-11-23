from PIL import Image
import os

# Source PNG icon
png_path = "icon.png"
ico_path = "icon.ico"

try:
    # Open the PNG file
    img = Image.open(png_path)
    print(f"Loaded {png_path}")
    print(f"Original size: {img.size}")
    print(f"Original mode: {img.mode}")
    
    # Convert to RGBA if not already
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Create high-quality ICO file with multiple sizes
    # Windows uses different sizes for different contexts:
    # - 256x256: High DPI displays, Windows 10/11 taskbar
    # - 128x128: Windows Explorer large icons
    # - 64x64: Windows Explorer medium icons
    # - 48x48: Windows Explorer default view
    # - 32x32: Windows Explorer small icons, title bar
    # - 16x16: Windows Explorer smallest icons
    
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    
    # Create a list to hold all the resized images
    icon_images = []
    
    for size in sizes:
        # Use LANCZOS for highest quality downsampling
        resized = img.resize(size, Image.Resampling.LANCZOS)
        icon_images.append(resized)
        print(f"  Created {size[0]}x{size[1]} version")
    
    # Save as ICO with all sizes
    # The first image in the list is used as the base
    icon_images[0].save(
        ico_path, 
        format='ICO', 
        sizes=sizes,
        append_images=icon_images[1:]
    )
    print(f"\n✅ Created high-quality {ico_path}")
    print(f"   Included sizes: {sizes}")
    
    # Verify the ICO file
    ico_verify = Image.open(ico_path)
    print(f"\n✅ Verified {ico_path}")
    print(f"   ICO size: {ico_verify.size}")
    print(f"   File size: {os.path.getsize(ico_path):,} bytes")
    
    # Create Wizard Images for Inno Setup with high quality
    print("\n📦 Creating installer wizard images...")
    
    # Large wizard image: 164x314
    large_bg = Image.new('RGB', (164, 314), (255, 255, 255))
    icon_large = img.resize((128, 128), Image.Resampling.LANCZOS)
    
    # Convert RGBA to RGB with white background
    if icon_large.mode == 'RGBA':
        bg = Image.new('RGB', icon_large.size, (255, 255, 255))
        bg.paste(icon_large, mask=icon_large.split()[3])
        icon_large = bg
    
    # Center the icon
    x = (164 - 128) // 2
    y = (314 - 128) // 2
    large_bg.paste(icon_large, (x, y))
    large_bg.save("wizard_large.bmp")
    print("✅ Created wizard_large.bmp (164x314)")
    
    # Small wizard image: 55x55
    small_bg = Image.new('RGB', (55, 55), (255, 255, 255))
    icon_small = img.resize((48, 48), Image.Resampling.LANCZOS)
    
    # Convert RGBA to RGB with white background
    if icon_small.mode == 'RGBA':
        bg = Image.new('RGB', icon_small.size, (255, 255, 255))
        bg.paste(icon_small, mask=icon_small.split()[3])
        icon_small = bg
    
    x = (55 - 48) // 2
    y = (55 - 48) // 2
    small_bg.paste(icon_small, (x, y))
    small_bg.save("wizard_small.bmp")
    print("✅ Created wizard_small.bmp (55x55)")
    
    print("\n🎉 All high-quality icon files created successfully!")
    print("\n📋 Summary:")
    print(f"   • icon.ico: {os.path.getsize(ico_path):,} bytes (multi-resolution)")
    print(f"   • wizard_large.bmp: {os.path.getsize('wizard_large.bmp'):,} bytes")
    print(f"   • wizard_small.bmp: {os.path.getsize('wizard_small.bmp'):,} bytes")
    print("\n💡 Next steps:")
    print("   1. Run: python -m PyInstaller Ninlab.spec")
    print("   2. Run: .\\build_installer.bat")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
