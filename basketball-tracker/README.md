# Basketball Shot Tracker - Web Dashboard Setup Guide

## 🏀 Overview
Real-time basketball shot tracking system with live web dashboard. Tracks ball position, speed, trajectory, and shot statistics.

## 📋 Requirements

### Hardware
- Raspberry Pi Zero 2 W (or any Raspberry Pi)
- Raspberry Pi AI Camera (CSI connection) OR USB webcam
- Power bank (5V, 2A minimum)
- Colored ball or marker for tracking

### Software
- Python 3.7+
- OpenCV
- Flask
- Flask-SocketIO

## 🚀 Installation

### Step 1: Install System Dependencies (Raspberry Pi)
```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-opencv
```

### Step 2: Install Python Packages
```bash
pip3 install --break-system-packages -r requirements.txt
```

Or install individually:
```bash
pip3 install --break-system-packages opencv-python numpy flask flask-socketio python-socketio eventlet
```

### Step 3: Verify Installation
```bash
python3 -c "import cv2; import flask; import socketio; print('All packages installed!')"
```

## 🎮 Usage

### Starting the Tracker

1. **Navigate to project directory:**
```bash
cd /path/to/basketball-tracker
```

2. **Run the tracker:**
```bash
python3 basketball_tracker_web.py
```

3. **Access the dashboard:**
   - On the same device: http://localhost:5000
   - From another device on network: http://[RASPBERRY_PI_IP]:5000
   - To find your Pi's IP: `hostname -I`

### Using the Dashboard

#### Initial Setup
1. **Calibrate the Hoop:**
   - Press 'h' in the camera window
   - Click on the center of the basketball hoop
   - Press 'c' to confirm

2. **Test Ball Detection:**
   - Use a colored ball or paper circle
   - Adjust lighting if needed
   - Ball should be detected with green circle outline

#### Dashboard Features

**Real-time Metrics:**
- Frame Rate (FPS)
- Distance to Hoop
- Current Ball Speed
- Maximum Speed Recorded

**Shot Statistics:**
- Total Shots Attempted
- Successful Shots (Made)
- Missed Shots
- Accuracy Percentage

**Performance Monitoring:**
- Frame Latency
- Detection Processing Time
- Drawing Time
- Positions Tracked

**Trajectory Visualization:**
- Live ball path display
- Hoop position marker
- Color-coded trail

#### Controls

**Web Dashboard:**
- "Reset Trajectory" button - Clear current ball path
- "Calibrate Hoop" button - Shows calibration instructions

**Keyboard (Camera Window):**
- `h` - Calibrate hoop position
- `r` - Reset trajectory
- `q` - Quit application

## 🎨 Customization

### Adjusting Color Detection

Edit the HSV color range in `basketball_tracker_web.py`:

```python
# For orange basketball:
self.lower_color = np.array([5, 100, 100])
self.upper_color = np.array([15, 255, 255])

# For green marker:
self.lower_color = np.array([35, 100, 100])
self.upper_color = np.array([75, 255, 255])

# For blue marker:
self.lower_color = np.array([100, 100, 100])
self.upper_color = np.array([130, 255, 255])
```

### Performance Optimization

For slower systems, adjust these parameters:

```python
# Reduce resolution
self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

# Skip more frames
self.frame_skip = 2  # Process every 2nd frame

# Reduce trajectory history
self.ball_positions = deque(maxlen=25)  # Store fewer positions
```

### Changing Web Server Port

In `basketball_tracker_web.py`:

```python
self.socketio.run(self.app, host='0.0.0.0', port=8080, debug=False)
```

## 🔧 Troubleshooting

### Camera Not Detected
```bash
# Test camera with OpenCV
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('Camera OK' if cap.isOpened() else 'Camera Error')"

# For Raspberry Pi Camera, try:
python3 -c "from picamera2 import Picamera2; cam = Picamera2(); print('Camera OK')"
```

### Low FPS / Performance Issues
- Reduce resolution in code
- Increase `frame_skip` value
- Use fewer trajectory points
- Close other applications
- Ensure adequate power supply

### Ball Not Detected
- Check lighting conditions
- Adjust HSV color range
- Use a more distinctly colored object
- Ensure object is large enough (min_ball_radius setting)

### Cannot Access Dashboard from Other Devices
```bash
# Check firewall
sudo ufw allow 5000

# Verify Pi's IP address
hostname -I

# Test connectivity
ping [PI_IP_ADDRESS]
```

### WebSocket Connection Issues
- Ensure Flask-SocketIO is installed correctly
- Check that port 5000 is not blocked
- Try accessing from http:// not https://

## 📱 Accessing from Mobile

1. Connect mobile device to same WiFi network as Raspberry Pi
2. Find Pi's IP address: `hostname -I`
3. Open mobile browser
4. Navigate to: `http://[PI_IP_ADDRESS]:5000`

## 🎯 Tips for Best Results

### Optimal Setup
- Good, even lighting
- Contrasting background
- Stable camera mount
- Clear view of hoop and shooting area
- Distinctive colored ball/marker

### Improving Accuracy
- Calibrate with actual hoop position
- Use consistent shooting location
- Ensure stable power supply
- Minimize camera movement
- Test different color ranges

### Future Enhancements
- Add trajectory prediction (parabolic fitting)
- Implement automatic shot detection (make/miss)
- Store shot history to database
- Add user profiles and statistics
- Mobile app integration
- Cloud synchronization

## 📊 Data Format

The system broadcasts JSON data via WebSocket:

```json
{
  "fps": 28.5,
  "frame_latency": 35.2,
  "detection_time": 12.4,
  "draw_time": 8.1,
  "distance": 2.45,
  "trajectory": [
    {"x": 320, "y": 240},
    {"x": 325, "y": 235}
  ],
  "hoop_position": [400, 200],
  "total_shots": 10,
  "made_shots": 7,
  "missed_shots": 3,
  "accuracy": 70.0,
  "current_speed": 3.2,
  "max_speed": 5.8,
  "positions_tracked": 45
}
```

## 🤝 Contributing

Feel free to enhance the project with:
- Better detection algorithms
- Machine learning integration
- Additional statistics
- UI improvements
- Performance optimizations

## 📝 License

Educational project for engineering class. Free to use and modify.

## 🆘 Support

For issues or questions:
1. Check troubleshooting section
2. Verify all dependencies installed
3. Test camera separately
4. Check system logs: `journalctl -xe`

---

**Happy Tracking! 🏀**
