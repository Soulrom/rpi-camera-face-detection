#!/bin/bash

# ============================================================================
# Raspberry Pi 4 B - Camera Stream Installation Script
# IMX290 IR-CUT + HTTP MJPEG Streaming with Face Detection
# ============================================================================

set -e

echo "[INSTALL] Raspberry Pi 4 B Camera Stream Setup"
echo "=============================================================="
echo ""

# Check for root
if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run as root (sudo)"
   exit 1
fi

echo "[STEP 1] Updating system packages..."
apt-get update
apt-get upgrade -y

echo ""
echo "[STEP 2] Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-libcamera \
    python3-picamera2 \
    libatlas-base-dev \
    libjasper-dev \
    libtiff5 \
    libopenjp2-7 \
    libharfbuzz0b \
    libwebp6 \
    v4l-utils

echo ""
echo "[STEP 3] Upgrading Python package manager..."
pip3 install --upgrade pip setuptools wheel

echo ""
echo "[STEP 4] Installing Python dependencies from requirements.txt..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
pip3 install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "[STEP 5] Setting up camera permissions..."
usermod -a -G video pi 2>/dev/null || true
usermod -a -G render pi 2>/dev/null || true
usermod -a -G kvm pi 2>/dev/null || true

echo ""
echo "[SUCCESS] Installation complete!"
echo ""
echo "=============================================================="
echo "Next steps:"
echo "  1. Reboot your Pi:  sudo reboot"
echo "  2. Run the camera: python3 ~/Camera/camera_rtsp_stream.py"
echo "  3. Open browser:   http://YOUR_PI_IP:5000"
echo ""
echo "For more info, see DEPLOY.md or README.md"
echo "=============================================================="

