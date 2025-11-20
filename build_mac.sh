#!/bin/bash
# Build script for creating Ninlab.app on macOS

echo "🚀 Building Ninlab for macOS..."

# Check if py2app is installed
if ! python -c "import py2app" 2>/dev/null; then
    echo "📦 Installing py2app..."
    pip install py2app
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist

# Build the app
echo "🔨 Building app bundle..."
python setup.py py2app

# Check if build was successful
if [ -d "dist/Ninlab.app" ]; then
    echo "✅ Build successful!"
    echo "📁 App location: $(pwd)/dist/Ninlab.app"
    echo ""
    echo "To install:"
    echo "  1. Open Finder and navigate to: $(pwd)/dist/"
    echo "  2. Drag Ninlab.app to your Applications folder"
    echo ""
    echo "Or run: open dist/"
else
    echo "❌ Build failed!"
    exit 1
fi
