#!/bin/bash
# =============================================
# Basketball Shot Tracker — Raspberry Pi Setup
# Run this ONCE on the Pi after cloning the repo
# Usage: bash setup.sh
# =============================================

echo ""
echo "======================================"
echo " Basketball Tracker — Pi Setup Script"
echo "======================================"
echo ""

# ── 1. System packages ────────────────────
echo ">>> Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    libopencv-dev \
    libatlas-base-dev \
    libjasper-dev \
    libhdf5-dev \
    libqtgui4 \
    libqt4-test \
    git \
    screen

echo "System packages installed"
echo ""

# ── 2. Python virtual environment ─────────
echo ">>> Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
echo "Virtual environment created"
echo ""

# ── 3. Python packages ────────────────────
echo ">>> Installing Python packages (this may take a few minutes on the Pi)..."
pip install --upgrade pip
pip install -r requirements.txt
echo "Python packages installed"
echo ""

# ── 4. Systemd service (auto-start on boot) ──
echo ">>> Setting up auto-start service..."

# Write the service file
sudo bash -c "cat > /etc/systemd/system/basketball-tracker.service << 'EOF'
[Unit]
Description=Basketball Shot Tracker
After=network.target

[Service]
ExecStart=/home/pi/EDDProjectCode/venv/bin/python /home/pi/EDDProjectCode/EDDProject.py
WorkingDirectory=/home/pi/EDDProjectCode
StandardOutput=append:/home/pi/EDDProjectCode/tracker.log
StandardError=append:/home/pi/EDDProjectCode/tracker.log
Restart=on-failure
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable basketball-tracker.service
echo "Auto-start service installed"
echo ""

# ── Done ──────────────────────────────────
echo "======================================"
echo " Setup complete!"
echo ""
echo " To start now:      bash start.sh"
echo " To start on boot:  already enabled"
echo " Dashboard:         http://$(hostname -I | awk '{print $1}'):8000"
echo " Logs:              tail -f /home/pi/EDDProjectCode/tracker.log"
echo "======================================"
echo ""
