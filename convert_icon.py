from PIL import Image
import os

# Source icon
ico_path = "icon.ico"

try:
    # Open the user-provided ICO
    img = Image.open(ico_path)
    print(f"Loaded icon.ico size: {img.size}")
    
    # Create Wizard Images for Inno Setup
    # WizardImageFile (Large): 164x314
    # WizardSmallImageFile (Small): 55x55
    
    # Create a white background for the large image
    large_bg = Image.new('RGB', (164, 314), (255, 255, 255))
    
    # Resize icon to fit nicely (e.g. 128x128) - use high quality resampling
    # We pick the largest frame from the ICO if possible, but Image.open usually gets one.
    # To be safe, we can try to find the largest size if it's a multi-size ICO, 
    # but Pillow's default open is usually fine for this resizing purpose.
    icon_large = img.resize((128, 128), Image.Resampling.LANCZOS)
    
    # Center the icon
    x = (164 - 128) // 2
    y = (314 - 128) // 2
    large_bg.paste(icon_large, (x, y))
    large_bg.save("wizard_large.bmp")
    print("✅ Created wizard_large.bmp")
    
    # Create small image
    small_bg = Image.new('RGB', (55, 55), (255, 255, 255))
    icon_small = img.resize((48, 48), Image.Resampling.LANCZOS)
    x = (55 - 48) // 2
    y = (55 - 48) // 2
    small_bg.paste(icon_small, (x, y))
    small_bg.save("wizard_small.bmp")
    print("✅ Created wizard_small.bmp")
    
except Exception as e:
    print(f"❌ Error: {e}")
