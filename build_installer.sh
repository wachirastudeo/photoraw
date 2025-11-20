#!/bin/bash
# Build Ninlab.app for distribution using PyInstaller

echo "🚀 Building Ninlab.app for macOS distribution..."

# Activate virtual environment
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found! Please run ./run_mac.sh first."
    exit 1
fi

source .venv/bin/activate

# Check if PyInstaller is installed
if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "📦 Installing PyInstaller..."
    pip install pyinstaller
fi

# Check if scipy is installed
if ! python -c "import scipy" 2>/dev/null; then
    echo "📦 Installing scipy..."
    pip install scipy
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist Ninlab.zip

# Build the app with all dependencies
echo "🔨 Building app bundle..."
pyinstaller --clean --noconfirm \
    --onedir \
    --windowed \
    --name=Ninlab \
    --icon=icon.ico \
    --add-data="icon.ico:." \
    --hidden-import=imaging \
    --hidden-import=workers \
    --hidden-import=ui_helpers \
    --hidden-import=catalog \
    --hidden-import=export_dialog \
    --hidden-import=cropper \
    --hidden-import=curve_widget \
    --hidden-import=scipy \
    --hidden-import=scipy.interpolate \
    --hidden-import=scipy.special \
    --hidden-import=scipy.linalg \
    main.py

# Check if build was successful
if [ -d "dist/Ninlab.app" ]; then
    echo "✅ Build successful!"
    echo "📁 App location: $(pwd)/dist/Ninlab.app"
    echo ""
    echo "Creating distribution package..."
    
    # Create zip file
    cd dist
    zip -r -q ../Ninlab.zip Ninlab.app
    cd ..
    
    echo "✅ Created Ninlab.zip ($(du -h Ninlab.zip | cut -f1))"
    echo ""
    echo "📦 Distribution files ready:"
    echo "  - Ninlab.app (in dist/ folder)"
    echo "  - Ninlab.zip (for sharing)"
    echo ""
    echo "To install:"
    echo "  1. Open Finder and navigate to: $(pwd)/dist/"
    echo "  2. Drag Ninlab.app to your Applications folder"
    echo ""
    echo "To share:"
    echo "  Send Ninlab.zip to others"
    echo "  They just need to extract and drag to Applications"
else
    echo "❌ Build failed!"
    exit 1
fi
