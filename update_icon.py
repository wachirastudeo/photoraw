from PIL import Image
import os

# Source PNG icon
png_path = "icon.png"
ico_path = "icon.ico"

try:
    # Open the PNG file
    img = Image.open(png_path)
    print(f"Loaded {png_path} size: {img.size}")
    
    # Convert to RGBA if not already
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Create ICO file with multiple sizes (256, 128, 64, 48, 32, 16)
    # Windows uses different sizes for different contexts
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    
    # Save as ICO with multiple resolutions
    img.save(ico_path, format='ICO', sizes=sizes)
    print(f"✅ Created {ico_path} with sizes: {sizes}")
    
    # Create Wizard Images for Inno Setup
    # WizardImageFile (Large): 164x314
    # WizardSmallImageFile (Small): 55x55
    
    # Create a white background for the large image
    large_bg = Image.new('RGB', (164, 314), (255, 255, 255))
    
    # Resize icon to fit nicely (e.g. 128x128) - use high quality resampling
    icon_large = img.resize((128, 128), Image.Resampling.LANCZOS)
    
    # Convert to RGB for BMP (remove alpha channel)
    if icon_large.mode == 'RGBA':
        # Create white background
        bg = Image.new('RGB', icon_large.size, (255, 255, 255))
        bg.paste(icon_large, mask=icon_large.split()[3])  # Use alpha channel as mask
        icon_large = bg
    
    # Center the icon
    x = (164 - 128) // 2
    y = (314 - 128) // 2
    large_bg.paste(icon_large, (x, y))
    large_bg.save("wizard_large.bmp")
    print("✅ Created wizard_large.bmp (164x314)")
    
    # Create small image
    small_bg = Image.new('RGB', (55, 55), (255, 255, 255))
    icon_small = img.resize((48, 48), Image.Resampling.LANCZOS)
    
    # Convert to RGB for BMP (remove alpha channel)
    if icon_small.mode == 'RGBA':
        bg = Image.new('RGB', icon_small.size, (255, 255, 255))
        bg.paste(icon_small, mask=icon_small.split()[3])
        icon_small = bg
    
    x = (55 - 48) // 2
    y = (55 - 48) // 2
    small_bg.paste(icon_small, (x, y))
    small_bg.save("wizard_small.bmp")
    print("✅ Created wizard_small.bmp (55x55)")
    
    print("\n🎉 All icon files updated successfully!")
    print("   - icon.ico (for application)")
    print("   - wizard_large.bmp (for installer)")
    print("   - wizard_small.bmp (for installer)")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
