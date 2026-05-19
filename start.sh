#!/bin/bash
# =============================================
# Basketball Shot Tracker — Start Script
# Run this any time you want to start the app
# Usage: bash start.sh
# =============================================

cd "$(dirname "$0")"
source venv/bin/activate

echo ""
echo "======================================"
echo " Basketball Tracker Starting..."
echo " Dashboard: http://$(hostname -I | awk '{print $1}'):8000"
echo " Press Ctrl+C to stop"
echo "======================================"
echo ""

python EDDProject.py
