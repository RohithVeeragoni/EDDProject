# 🏀 Basketball Shot Tracker - Quick Start

## 📦 Installation (One-Time Setup)

### For Raspberry Pi with CSI Camera:
```bash
# Install system packages
sudo apt-get update
sudo apt-get install -y python3-pip python3-opencv

# Install Python packages
pip3 install --break-system-packages -r requirements.txt

# For Raspberry Pi Camera support
pip3 install --break-system-packages picamera2
```

### For USB Camera (any system):
```bash
# Install Python packages
pip3 install -r requirements.txt
```

## 🚀 Running the Tracker

### Raspberry Pi with CSI Camera (Recommended):
```bash
python3 basketball_tracker_pi.py
```

### USB Camera:
```bash
python3 basketball_tracker_pi.py --usb
# OR
python3 basketball_tracker_web.py
```

## 🌐 Accessing the Dashboard

1. **On the same device:**
   - Open browser to: `http://localhost:5000`

2. **From phone/tablet/computer on same network:**
   - Find your Raspberry Pi's IP: `hostname -I`
   - Open browser to: `http://[PI_IP]:5000`
   - Example: `http://192.168.1.100:5000`

## ⚙️ Quick Configuration

### 1. Calibrate Hoop Position
- Start the tracker
- Press `h` key in camera window
- Click on the hoop center
- Press `c` to confirm

### 2. Adjust Color Detection (if needed)

Edit the color range in the Python file:

**For Orange Basketball:**
```python
self.lower_color = np.array([5, 100, 100])
self.upper_color = np.array([15, 255, 255])
```

**For Green Marker:**
```python
self.lower_color = np.array([35, 100, 100])
self.upper_color = np.array([75, 255, 255])
```

**For Blue Marker:**
```python
self.lower_color = np.array([100, 100, 100])
self.upper_color = np.array([130, 255, 255])
```

## 📊 What You'll See on Dashboard

- **Frame Rate** - Real-time FPS
- **Distance to Hoop** - In meters (after calibration)
- **Ball Speed** - Current and maximum
- **Shot Statistics** - Total, made, missed, accuracy %
- **Trajectory Visualization** - Live ball path
- **Performance Metrics** - System performance data

## 🎮 Controls

### Web Dashboard:
- **Reset Trajectory** button - Clear current path
- **Calibrate Hoop** button - Instructions for hoop setup

### Keyboard (when camera window is active):
- `h` - Calibrate hoop position
- `r` - Reset trajectory
- `q` - Quit application

## ⚡ Quick Fixes

### "Camera not found"
```bash
# Check camera connection
ls -l /dev/video*

# Test camera
python3 test_installation.py
```

### "Port already in use"
```bash
# Kill process using port 5000
sudo lsof -ti:5000 | xargs kill -9
```

### Low FPS / Laggy
Edit the Python file and change:
```python
self.frame_skip = 2  # Process every 2nd frame instead of every frame
```

### Ball not detected
- Ensure good lighting
- Use a distinctly colored object
- Adjust HSV color range in code
- Check object size is within min/max radius settings

## 📱 Mobile Access Tips

1. **Connect to same WiFi** as Raspberry Pi
2. **Use IP address**, not localhost
3. **Use http://**, not https://
4. **Portrait or landscape** - dashboard responsive

## 🎯 Best Practices

✅ **Good Setup:**
- Even, bright lighting
- Contrasting background
- Stable camera mount
- Clear hoop view
- Distinctive ball color

❌ **Avoid:**
- Backlit scenes
- Moving camera
- Similar colored backgrounds
- Poor lighting
- Camera too far from action

## 🔧 Testing Installation

Run the test script to verify everything is working:
```bash
python3 test_installation.py
```

This will check:
- Python packages installed
- Camera accessible
- Network port available
- Required files present

## 📚 Full Documentation

See `README.md` for complete documentation including:
- Detailed installation steps
- Full troubleshooting guide
- Advanced configuration
- Data format specifications
- Future enhancement ideas

## 🆘 Need Help?

1. Run test script: `python3 test_installation.py`
2. Check README.md troubleshooting section
3. Verify camera works: `libcamera-hello` (Pi Camera)
4. Check system logs: `journalctl -xe`

---

**Ready to track some shots! 🏀🎯**
