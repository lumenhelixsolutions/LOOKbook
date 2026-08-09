#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "==> Initializing MoneyPrinterTurbo submodule..."
cd "$ROOT_DIR"
git submodule update --init --recursive -- tools/moneyprinter

echo "==> Installing MoneyPrinterTurbo dependencies..."
cd "$ROOT_DIR/tools/moneyprinter"
if command -v uv &> /dev/null; then
    uv pip install -r requirements.txt
elif command -v pip &> /dev/null; then
    pip install -r requirements.txt
else
    echo "ERROR: Neither uv nor pip found. Please install Python packaging tools."
    exit 1
fi

echo "==> Linking lookBOOK config..."
mkdir -p "$ROOT_DIR/config"
if [ ! -f "$ROOT_DIR/config/moneyprinter.toml" ]; then
    cp "$ROOT_DIR/config/moneyprinter.toml" "$ROOT_DIR/tools/moneyprinter/config.toml" 2>/dev/null || true
fi

echo "==> MoneyPrinterTurbo ready."
echo "    Start: cd tools/moneyprinter && python main.py"
