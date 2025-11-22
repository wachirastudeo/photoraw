from PIL import Image
import sys
import os

def convert_to_ico(source_path, dest_path="icon.ico"):
    if not os.path.exists(source_path):
        print(f"Error: {source_path} not found")
        return

    try:
        img = Image.open(source_path)
        # Ensure we start with high quality
        if img.width < 256 or img.height < 256:
            print(f"Warning: Source image is small ({img.width}x{img.height}), upscaling may be blurry.")
        
        # Create icon with multiple sizes using high-quality resampling
        # We manually resize to ensure quality control
        images = []
        for size in [256, 128, 64, 48, 32, 16]:
            if size <= img.width: # Only downscale, never upscale blindly unless needed
                res = img.resize((size, size), Image.Resampling.LANCZOS)
                images.append(res)
            else:
                # If source is smaller than target, keep source or upscale carefully
                res = img.resize((size, size), Image.Resampling.LANCZOS)
                images.append(res)

        # Save as ICO containing all generated sizes
        images[0].save(dest_path, format='ICO', sizes=[(i.width, i.height) for i in images], append_images=images[1:])
        print(f"Successfully converted {source_path} to {dest_path} with multiple sizes.")
    except Exception as e:
        print(f"Error converting icon: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        convert_to_ico(sys.argv[1])
    else:
        # Try to find a source image if not specified
        possible_sources = ["icon.png", "logo.png", "icon.jpg", "logo.jpg"]
        found = False
        for src in possible_sources:
            if os.path.exists(src):
                convert_to_ico(src)
                found = True
                break
        
        if not found:
            print("Usage: python make_ico.py <source_image_path>")
            print("Or place 'icon.png' in this folder.")
