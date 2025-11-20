#!/bin/bash
# Run Ninlab on macOS

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Creating virtual environment..."
    python3 -m venv .venv
    
    echo "Installing dependencies..."
    source .venv/bin/activate
    pip install --upgrade pip
    pip install PySide6 numpy pillow rawpy scipy
else
    source .venv/bin/activate
fi

# Check if scipy is installed
if ! python -c "import scipy" 2>/dev/null; then
    echo "📦 Installing scipy..."
    pip install scipy
fi

# Run the application
echo "🚀 Starting Ninlab..."
python main.py
