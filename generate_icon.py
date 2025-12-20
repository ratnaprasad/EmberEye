"""Generate Windows .ico file from logo.png for branded executable.

Usage:
  python generate_icon.py

Requires: Pillow (pip install Pillow)
Generates: logo.ico (multi-resolution icon for Windows)
"""
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)


def generate_icon():
    logo_path = 'logo.png'
    if not os.path.exists(logo_path):
        print(f"ERROR: {logo_path} not found. Create a logo first.")
        sys.exit(1)
    
    img = Image.open(logo_path)
    
    # Convert RGBA if needed
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Generate multi-resolution icon (16, 32, 48, 64, 128, 256)
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Resize for each resolution
    resized = []
    for size in icon_sizes:
        resized.append(img.resize(size, Image.Resampling.LANCZOS))
    
    # Save as .ico
    output = 'logo.ico'
    resized[0].save(output, format='ICO', sizes=[s for s in icon_sizes])
    
    print(f"✓ Generated {output} with {len(icon_sizes)} resolutions")
    print(f"  Sizes: {', '.join([f'{s[0]}x{s[1]}' for s in icon_sizes])}")
    
    # Verify
    if os.path.exists(output):
        size_kb = os.path.getsize(output) / 1024
        print(f"  File size: {size_kb:.1f} KB")
        return True
    return False


if __name__ == '__main__':
    if generate_icon():
        print("\nIcon ready for PyInstaller (EmberEye_win.spec will use it)")
    else:
        print("\nIcon generation failed")
        sys.exit(1)
