from PIL import Image
import sys

def inspect_icon(path):
    try:
        img = Image.open(path)
        print(f"Inspecting: {path}")
        print(f"Format: {img.format}")
        print(f"Sizes found in ICO:")
        
        # ICO files in PIL contain multiple frames
        # We can iterate through them
        try:
            i = 0
            while True:
                img.seek(i)
                print(f"  Layer {i}: {img.size} - Mode: {img.mode}")
                i += 1
        except EOFError:
            pass
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_icon("icon.ico")
