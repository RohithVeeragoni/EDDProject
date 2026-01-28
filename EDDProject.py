import cv2
import numpy as np
from collections import deque
import time
from flask import Flask, render_template_string, Response
from flask_socketio import SocketIO, emit
import threading
import json
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'basketball_tracker_secret'
socketio = SocketIO(app, cors_allowed_origins="*")

class BasketballTracker:
    def __init__(self, camera_index=0):
        """
        Initialize the basketball tracking system with web interface
        """
        # Camera setup
        self.cap = cv2.VideoCapture(camera_index)
        
        # Optimize for Raspberry Pi
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        # Color range for the colored circles (HSV)
        self.lower_color = np.array([35, 100, 100])
        self.upper_color = np.array([75, 255, 255])
        
        # Ball tracking parameters
        self.ball_positions = deque(maxlen=50)
        self.min_ball_radius = 5
        self.max_ball_radius = 150
        
        # Hoop calibration
        self.hoop_position = None
        self.pixels_per_meter = None
        
        # Frame processing
        self.frame_skip = 1
        self.frame_count = 0
        
        # Timing and performance metrics
        self.fps = 0
        self.frame_times = deque(maxlen=30)
        self.last_frame_time = time.time()
        self.frame_latency = 0
        self.detection_time = 0
        self.draw_time = 0
        
        # Web dashboard data
        self.current_frame = None
        self.current_distance = 0
        self.is_running = False
        
        # Shot statistics
        self.total_shots = 0
        self.made_shots = 0
        self.missed_shots = 0
        
    def detect_ball(self, frame):
        """Detect the colored circle in frame"""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.lower_color, self.upper_color)
        
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=2)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if len(contours) > 0:
            largest_contour = max(contours, key=cv2.contourArea)
            ((x, y), radius) = cv2.minEnclosingCircle(largest_contour)
            
            if self.min_ball_radius < radius < self.max_ball_radius:
                return (int(x), int(y), int(radius))
        
        return None
    
    def calculate_distance_from_hoop(self, ball_pos):
        """Calculate distance from ball to hoop in meters"""
        if self.hoop_position is None or self.pixels_per_meter is None:
            return None
        
        pixel_distance = np.sqrt(
            (ball_pos[0] - self.hoop_position[0])**2 + 
            (ball_pos[1] - self.hoop_position[1])**2
        )
        
        return pixel_distance / self.pixels_per_meter
    
    def draw_info(self, frame, ball_info):
        """Draw tracking information on frame"""
        if self.hoop_position is not None:
            cv2.circle(frame, self.hoop_position, 10, (0, 255, 0), 2)
            cv2.putText(frame, "HOOP", 
                       (self.hoop_position[0] - 20, self.hoop_position[1] - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        if ball_info is not None:
            x, y, radius = ball_info
            cv2.circle(frame, (x, y), radius, (0, 0, 255), 2)
            cv2.circle(frame, (x, y), 3, (0, 0, 255), -1)
            
            # Draw trajectory
            for i in range(1, len(self.ball_positions)):
                if self.ball_positions[i-1] is None or self.ball_positions[i] is None:
                    continue
                cv2.line(frame, self.ball_positions[i-1], self.ball_positions[i],
                        (255, 0, 0), 2)
            
            distance = self.calculate_distance_from_hoop((x, y))
            if distance is not None:
                self.current_distance = distance
                cv2.putText(frame, f"Distance: {distance:.2f}m",
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Display performance metrics
        cv2.putText(frame, f"FPS: {self.fps:.1f}",
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Latency: {self.frame_latency*1000:.1f}ms",
                   (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        return frame
    
    def get_dashboard_data(self):
        """Get data for web dashboard"""
        return {
            'fps': round(self.fps, 1),
            'frame_latency': round(self.frame_latency * 1000, 1),
            'detection_time': round(self.detection_time * 1000, 1),
            'draw_time': round(self.draw_time * 1000, 1),
            'distance': round(self.current_distance, 2),
            'positions_tracked': len([p for p in self.ball_positions if p is not None]),
            'total_shots': self.total_shots,
            'made_shots': self.made_shots,
            'missed_shots': self.missed_shots,
            'accuracy': round((self.made_shots / self.total_shots * 100) if self.total_shots > 0 else 0, 1)
        }
    
    def process_frame(self):
        """Process a single frame and return it"""
        loop_start = time.time()
        
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        # Calculate frame latency
        current_time = time.time()
        self.frame_latency = current_time - self.last_frame_time
        self.last_frame_time = current_time
        self.frame_times.append(self.frame_latency)
        
        # Calculate FPS
        if len(self.frame_times) > 0:
            avg_frame_time = sum(self.frame_times) / len(self.frame_times)
            self.fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
        
        self.frame_count += 1
        
        # Measure detection time
        detect_start = time.time()
        ball_info = self.detect_ball(frame)
        self.detection_time = time.time() - detect_start
        
        # Update trajectory
        if ball_info is not None:
            self.ball_positions.append((ball_info[0], ball_info[1]))
        else:
            self.ball_positions.append(None)
        
        # Measure drawing time
        draw_start = time.time()
        display_frame = self.draw_info(frame, ball_info)
        self.draw_time = time.time() - draw_start
        
        self.current_frame = display_frame
        
        return display_frame
    
    def run_headless(self):
        """Run tracker without OpenCV window (for web only)"""
        print("Basketball Tracker started in web mode")
        print("View dashboard at: http://localhost:5000")
        
        self.is_running = True
        
        while self.is_running:
            frame = self.process_frame()
            
            if frame is None:
                break
            
            # Send data to web dashboard every 10 frames
            if self.frame_count % 10 == 0:
                data = self.get_dashboard_data()
                socketio.emit('update_data', data, namespace='/')
            
            time.sleep(0.001)  # Small delay to prevent CPU overload
    
    def cleanup(self):
        """Release resources"""
        self.is_running = False
        self.cap.release()
        print("Tracker stopped")

# Global tracker instance
tracker = None

# HTML Template with embedded CSS and JavaScript
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Basketball Shot Tracker</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        h1 {
            text-align: center;
            font-size: 3em;
            margin-bottom: 30px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .metric-card {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            border: 2px solid rgba(255, 255, 255, 0.2);
            transition: transform 0.3s;
        }
        
        .metric-card:hover {
            transform: translateY(-5px);
            border-color: rgba(255, 255, 255, 0.4);
        }
        
        .metric-label {
            font-size: 0.9em;
            opacity: 0.8;
            margin-bottom: 10px;
        }
        
        .metric-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #4ade80;
        }
        
        .status {
            text-align: center;
            padding: 15px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 10px;
            margin-bottom: 20px;
        }
        
        .status.connected {
            background: rgba(74, 222, 128, 0.2);
            border: 2px solid #4ade80;
        }
        
        .status.disconnected {
            background: rgba(239, 68, 68, 0.2);
            border: 2px solid #ef4444;
        }
        
        .shot-stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 20px;
        }
        
        .stat-box {
            background: rgba(0, 0, 0, 0.3);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
        }
        
        .stat-box h3 {
            font-size: 0.9em;
            opacity: 0.8;
            margin-bottom: 8px;
        }
        
        .stat-box .value {
            font-size: 2em;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏀 Basketball Shot Tracker</h1>
        
        <div id="status" class="status disconnected">
            ⚠️ Connecting to tracker...
        </div>
        
        <div class="dashboard">
            <div class="metric-card">
                <div class="metric-label">FPS</div>
                <div class="metric-value" id="fps">0</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Frame Latency</div>
                <div class="metric-value" id="latency">0 <span style="font-size: 0.5em;">ms</span></div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Detection Time</div>
                <div class="metric-value" id="detection">0 <span style="font-size: 0.5em;">ms</span></div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Distance from Hoop</div>
                <div class="metric-value" id="distance">0 <span style="font-size: 0.5em;">m</span></div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Positions Tracked</div>
                <div class="metric-value" id="positions">0</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Accuracy</div>
                <div class="metric-value" id="accuracy">0 <span style="font-size: 0.5em;">%</span></div>
            </div>
        </div>
        
        <div class="shot-stats">
            <div class="stat-box">
                <h3>Total Shots</h3>
                <div class="value" id="total-shots">0</div>
            </div>
            <div class="stat-box">
                <h3>Makes</h3>
                <div class="value" id="made-shots" style="color: #4ade80;">0</div>
            </div>
            <div class="stat-box">
                <h3>Misses</h3>
                <div class="value" id="missed-shots" style="color: #ef4444;">0</div>
            </div>
        </div>
    </div>
    
    <script>
        const socket = io();
        
        socket.on('connect', function() {
            document.getElementById('status').className = 'status connected';
            document.getElementById('status').innerHTML = '✅ Connected to tracker';
        });
        
        socket.on('disconnect', function() {
            document.getElementById('status').className = 'status disconnected';
            document.getElementById('status').innerHTML = '⚠️ Disconnected from tracker';
        });
        
        socket.on('update_data', function(data) {
            document.getElementById('fps').textContent = data.fps;
            document.getElementById('latency').innerHTML = data.frame_latency + ' <span style="font-size: 0.5em;">ms</span>';
            document.getElementById('detection').innerHTML = data.detection_time + ' <span style="font-size: 0.5em;">ms</span>';
            document.getElementById('distance').innerHTML = data.distance + ' <span style="font-size: 0.5em;">m</span>';
            document.getElementById('positions').textContent = data.positions_tracked;
            document.getElementById('accuracy').innerHTML = data.accuracy + ' <span style="font-size: 0.5em;">%</span>';
            document.getElementById('total-shots').textContent = data.total_shots;
            document.getElementById('made-shots').textContent = data.made_shots;
            document.getElementById('missed-shots').textContent = data.missed_shots;
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'data': 'Connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

def run_tracker():
    """Run the tracker in a separate thread"""
    global tracker
    tracker = BasketballTracker(camera_index=0)
    tracker.run_headless()

if __name__ == "__main__":
    print("\n=== BASKETBALL SHOT TRACKER WEB DASHBOARD ===")
    print("Starting web server on http://localhost:5000")
    print("Open this URL in your browser to view the dashboard")
    print("Press Ctrl+C to stop")
    print("=" * 45 + "\n")
    
    # Start tracker in separate thread
    tracker_thread = threading.Thread(target=run_tracker, daemon=True)
    tracker_thread.start()
    
    # Start Flask web server
    socketio.run(app, host='0.0.0.0', port=8000, debug=False)