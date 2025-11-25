#!/bin/bash
# Start Jupyter Lab for Ablage-System experiments

set -e

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Jupyter Lab for Ablage-System${NC}"

# Check if in virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠ Warning: Not in a virtual environment${NC}"
    echo "Activate virtual environment first: source venv/bin/activate"
    exit 1
fi

# Check if jupyter is installed
if ! command -v jupyter &> /dev/null; then
    echo -e "${YELLOW}📦 Installing Jupyter Lab...${NC}"
    pip install jupyterlab ipykernel
fi

# Install kernel if not exists
KERNEL_NAME="ablage-ocr"
if ! jupyter kernelspec list | grep -q "$KERNEL_NAME"; then
    echo -e "${BLUE}🔧 Installing Jupyter kernel: $KERNEL_NAME${NC}"
    python -m ipykernel install --user --name="$KERNEL_NAME" --display-name="Python 3.11 (Ablage OCR)"
fi

# Create notebooks directory if it doesn't exist
if [ ! -d "notebooks" ]; then
    echo -e "${BLUE}📁 Creating notebooks directory${NC}"
    mkdir -p notebooks/{experiments,analysis,prototypes,tutorials,templates,results}
fi

# Port
PORT=${1:-8888}

echo ""
echo -e "${GREEN}✅ Starting Jupyter Lab${NC}"
echo -e "${BLUE}📊 Notebook directory: notebooks/${NC}"
echo -e "${BLUE}🌐 URL: http://localhost:$PORT${NC}"
echo ""
echo -e "${YELLOW}💡 Tip: Use templates in notebooks/templates/ to get started${NC}"
echo ""

# Start Jupyter Lab
jupyter lab \
    --notebook-dir=notebooks \
    --port=$PORT \
    --no-browser \
    --ServerApp.token='' \
    --ServerApp.password='' \
    --ServerApp.allow_origin='*'
