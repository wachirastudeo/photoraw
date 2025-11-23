from PIL import Image
import os

# Extract PNG from ICNS
icns_path = "icon.icns"
ico_path = "icon.ico"

# Read ICNS file (it contains multiple PNG images)
# We'll extract the largest one
with open(icns_path, 'rb') as f:
    icns_data = f.read()

# ICNS format: find the largest icon (usually 512x512 or 1024x1024)
# ICNS uses 'ic10' for 1024x1024 retina, 'ic09' for 512x512 retina
# We'll try to extract using Pillow's ICNS support

try:
    # Pillow can read ICNS directly
    img = Image.open(icns_path)
    
    # Get the largest size available
    # ICNS files contain multiple sizes, Pillow opens the largest by default
    print(f"Loaded icon size: {img.size}")
    
    # Create multiple sizes for ICO (Windows needs 16, 32, 48, 256)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Save as high-quality ICO with multiple resolutions
    img.save(ico_path, format='ICO', sizes=sizes)
    
    print(f"✅ Created high-quality icon.ico with sizes: {sizes}")
    
    # Create Wizard Images for Inno Setup
    # WizardImageFile (Large): 164x314
    # WizardSmallImageFile (Small): 55x55
    
    # Create a white background for the large image
    large_bg = Image.new('RGB', (164, 314), (255, 255, 255))
    # Resize icon to fit nicely (e.g. 128x128)
    icon_large = img.resize((128, 128), Image.Resampling.LANCZOS)
    # Center the icon
    x = (164 - 128) // 2
    y = (314 - 128) // 2
    large_bg.paste(icon_large, (x, y), icon_large)
    large_bg.save("wizard_large.bmp")
    print("✅ Created wizard_large.bmp")
    
    # Create small image
    small_bg = Image.new('RGB', (55, 55), (255, 255, 255))
    icon_small = img.resize((48, 48), Image.Resampling.LANCZOS)
    x = (55 - 48) // 2
    y = (55 - 48) // 2
    small_bg.paste(icon_small, (x, y), icon_small)
    small_bg.save("wizard_small.bmp")
    print("✅ Created wizard_small.bmp")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("Trying alternative method...")
    
    # Alternative: Use PNG extraction
    # ICNS 'ic10' = 1024x1024@2x, 'ic09' = 512x512@2x
    # We'll look for these tags
    
    # Simple ICNS parser
    offset = 0
    icons = {}
    
    while offset < len(icns_data) - 8:
        # Read type (4 bytes) and length (4 bytes)
        icon_type = icns_data[offset:offset+4].decode('ascii', errors='ignore')
        icon_length = int.from_bytes(icns_data[offset+4:offset+8], 'big')
        
        if icon_length < 8 or offset + icon_length > len(icns_data):
            break
            
        # Extract icon data
        icon_data = icns_data[offset+8:offset+icon_length]
        icons[icon_type] = icon_data
        
        offset += icon_length
    
    print(f"Found icon types: {list(icons.keys())}")
    
    # Try to find the best quality icon
    # Priority: ic10 (1024x1024@2x) > ic09 (512x512@2x) > ic08 (256x256)
    best_type = None
    for t in ['ic10', 'ic09', 'ic14', 'ic08', 'ic07']:
        if t in icons:
            best_type = t
            break
    
    if best_type:
        print(f"Using {best_type} for conversion")
        from io import BytesIO
        png_img = Image.open(BytesIO(icons[best_type]))
        
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        png_img.save(ico_path, format='ICO', sizes=sizes)
        
        print(f"✅ Created high-quality icon.ico")
        
        # Create Wizard Images for Inno Setup
        # WizardImageFile (Large): 164x314 (recommended)
        # WizardSmallImageFile (Small): 55x55 (recommended)
        
        # Create a white background for the large image
        large_bg = Image.new('RGB', (164, 314), (255, 255, 255))
        # Resize icon to fit nicely (e.g. 128x128)
        icon_large = png_img.resize((128, 128), Image.Resampling.LANCZOS)
        # Center the icon
        x = (164 - 128) // 2
        y = (314 - 128) // 2
        large_bg.paste(icon_large, (x, y), icon_large)
        large_bg.save("wizard_large.bmp")
        print("✅ Created wizard_large.bmp")
        
        # Create small image
        small_bg = Image.new('RGB', (55, 55), (255, 255, 255))
        icon_small = png_img.resize((48, 48), Image.Resampling.LANCZOS)
        x = (55 - 48) // 2
        y = (55 - 48) // 2
        small_bg.paste(icon_small, (x, y), icon_small)
        small_bg.save("wizard_small.bmp")
        print("✅ Created wizard_small.bmp")

