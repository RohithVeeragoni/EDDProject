import cv2
import numpy as np
from collections import deque
import time
from flask import Flask, render_template, Response
from flask_socketio import SocketIO, emit
import threading

app = Flask(__name__, template_folder='basketball-tracker/templates')
app.config['SECRET_KEY'] = 'basketball_tracker_secret'
app.config['TEMPLATES_AUTO_RELOAD'] = True

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class BasketballTracker:
    def __init__(self, camera_index=0):

        # ── Camera source ──────────────────────────────────────────────
        USE_LIMELIGHT = True
        self.cap = None

        if USE_LIMELIGHT:
            limelight_urls = [
                "http://limelight.local:5800/stream.mjpeg",
                "http://limelight.local:5800",
                "http://limelight.local:5801/stream.mjpeg",
                "http://limelight.local:5801",
            ]
            for url in limelight_urls:
                print(f"Trying Limelight stream: {url}")
                cap = cv2.VideoCapture(url)
                ret, frame = cap.read()
                if ret and frame is not None:
                    self.cap = cap
                    print(f"Connected to Limelight at: {url}")
                    break
                else:
                    cap.release()
                    print(f"No response from: {url}")

            if self.cap is None:
                print("Could not reach Limelight. Falling back to MacBook camera.")
                self.cap = cv2.VideoCapture(0)
                USE_LIMELIGHT = False
        else:
            self.cap = cv2.VideoCapture(0)

        # ── Resolution ────────────────────────────────────────────────
        if USE_LIMELIGHT:
            self.frame_width  = 1280
            self.frame_height = 960
        else:
            self.frame_width  = 1280
            self.frame_height = 720

        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # ── HSV color range for ball detection ────────────────────────
        self.lower_color = np.array([140, 40, 40])
        self.upper_color = np.array([180, 255, 255])

        # ── Ball tracking state ───────────────────────────────────────
        self.ball_positions  = deque(maxlen=50)
        self.ball_timestamps = deque(maxlen=50)
        self.min_ball_radius = 3
        self.max_ball_radius = 200

        # Velocity-based predictive tracking
        self.last_valid_position     = None
        self.last_valid_velocity     = (0, 0)
        self.missed_detections       = 0
        self.max_missed_before_reset = 10

        # ── Scale calibration ─────────────────────────────────────────
        self.hoop_position      = None
        self.ground_position    = None
        self.pixels_per_meter   = 100
        self.scale_calibrated   = False
        self.HOOP_HEIGHT_METERS = 3.048   # NBA standard: 10 ft

        # ── Depth estimation ──────────────────────────────────────────
        self.camera_focal_length = 800
        self.real_ball_diameter  = 0.24
        self.depth_calibrated     = False
        self.current_depth        = None
        self.last_detected_radius = None

        # ── Performance metrics ───────────────────────────────────────
        self.fps             = 0
        self.frame_times     = deque(maxlen=30)
        self.last_frame_time = time.time()
        self.frame_latency   = 0
        self.detection_time  = 0
        self.draw_time       = 0
        self.frame_count     = 0

        # ── Dashboard state ───────────────────────────────────────────
        self.current_frame    = None
        self.current_distance = 0
        self.is_running       = False
        self.max_speed        = 0
        self.current_speed    = 0
        self.current_angle    = 0
        self.launch_angle     = None

        # ── Shot statistics ───────────────────────────────────────────
        self.total_shots  = 0
        self.made_shots   = 0
        self.missed_shots = 0
        self.shot_log     = deque(maxlen=50)

        # ── Trajectory regression state ───────────────────────────────
        self.trajectory_coefficients = None
        self.predicted_outcome       = None
        self.predicted_landing_x     = None
        self.apex_height             = None
        self.apex_position           = None
        self.entry_angle             = None

        # ── Shot detection state machine ──────────────────────────────
        self.shot_in_progress    = False
        self.last_detection_time = time.time()
        self.shot_timeout        = 2.0

        # ── Thread safety ─────────────────────────────────────────────
        self.frame_lock = threading.Lock()

    # ── Ball detection ─────────────────────────────────────────────────
    def detect_ball(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Saturation boost to compensate for Limelight's flat color output
        SATURATION_BOOST = 1.6
        hsv_float = hsv.astype(np.float32)
        hsv_float[:, :, 1] = np.clip(hsv_float[:, :, 1] * SATURATION_BOOST, 0, 255)
        hsv = hsv_float.astype(np.uint8)

        mask = cv2.inRange(hsv, self.lower_color, self.upper_color)

        # Minimal morphological opening to preserve fast-motion blobs
        kernel = np.ones((2, 2), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_detection = None

        if len(contours) > 0:
            # Check top 3 contours by area
            for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
                area = cv2.contourArea(contour)
                if area > 50:
                    ((x, y), radius) = cv2.minEnclosingCircle(contour)
                    if self.min_ball_radius < radius < self.max_ball_radius:
                        if self.last_valid_position is not None:
                            # Prefer detections near the predicted position
                            predicted_x = self.last_valid_position[0] + self.last_valid_velocity[0]
                            predicted_y = self.last_valid_position[1] + self.last_valid_velocity[1]
                            distance_from_prediction = np.sqrt(
                                (x - predicted_x)**2 + (y - predicted_y)**2
                            )
                            if distance_from_prediction < 100:
                                best_detection = (int(x), int(y), int(radius))
                                break
                        else:
                            best_detection = (int(x), int(y), int(radius))
                            break

        if best_detection:
            x, y, radius = best_detection

            # Update velocity vector for next-frame prediction
            if self.last_valid_position is not None:
                self.last_valid_velocity = (
                    x - self.last_valid_position[0],
                    y - self.last_valid_position[1]
                )
            self.last_valid_position = (x, y)
            self.missed_detections   = 0

            depth = self.estimate_depth_from_ball_size(radius)
            self.current_depth       = depth
            self.last_detected_radius = radius
            return (x, y, radius, depth)

        else:
            self.missed_detections += 1

            # Gap-fill up to 5 frames using last known velocity
            if self.missed_detections < 5 and self.last_valid_position is not None:
                predicted_x = int(self.last_valid_position[0] + self.last_valid_velocity[0])
                predicted_y = int(self.last_valid_position[1] + self.last_valid_velocity[1])
                last_radius = 15
                self.last_valid_position = (predicted_x, predicted_y)
                return (predicted_x, predicted_y, last_radius, None)

            if self.missed_detections > self.max_missed_before_reset:
                self.last_valid_position  = None
                self.last_valid_velocity  = (0, 0)
                self.missed_detections    = 0

        return None

    # ── Speed and angle ────────────────────────────────────────────────
    def calculate_speed_and_angle(self):
        if len(self.ball_positions) < 2:
            return 0, 0

        valid_positions = [(pos, ts) for pos, ts in zip(self.ball_positions, self.ball_timestamps) if pos is not None]
        if len(valid_positions) < 2:
            return 0, 0

        num_points = min(5, len(valid_positions))
        recent_positions = valid_positions[-num_points:]

        total_distance = 0
        total_time     = 0

        for i in range(1, len(recent_positions)):
            pos1, t1 = recent_positions[i-1]
            pos2, t2 = recent_positions[i]
            pixel_dist  = np.sqrt((pos2[0] - pos1[0])**2 + (pos2[1] - pos1[1])**2)
            meter_dist  = pixel_dist / self.pixels_per_meter
            time_diff   = t2 - t1
            total_distance += meter_dist
            total_time     += time_diff

        speed = total_distance / total_time if total_time > 0 else 0

        if len(valid_positions) >= 2:
            pos1, _ = valid_positions[-2]
            pos2, _ = valid_positions[-1]
            dx    = pos2[0] - pos1[0]
            dy    = pos2[1] - pos1[1]
            angle = np.degrees(np.arctan2(-dy, dx))
            return speed, angle

        return speed, 0

    def calculate_launch_angle(self):
        valid_positions = [pos for pos in self.ball_positions if pos is not None]
        if len(valid_positions) >= 3:
            pos1 = valid_positions[0]
            pos3 = valid_positions[2]
            dx    = pos3[0] - pos1[0]
            dy    = pos3[1] - pos1[1]
            angle = np.degrees(np.arctan2(-dy, dx))
            return angle
        return None

    # ── Trajectory regression ──────────────────────────────────────────
    def get_valid_trajectory_data(self):
        valid_data = [
            (pos, t) for pos, t in zip(self.ball_positions, self.ball_timestamps)
            if pos is not None
        ]
        if len(valid_data) < 3:
            return None, None, None

        x_coords = [pos[0] for pos, t in valid_data]
        y_coords = [pos[1] for pos, t in valid_data]
        times    = [t      for pos, t in valid_data]
        return x_coords, y_coords, times

    def fit_trajectory(self):
        x_coords, y_coords, _ = self.get_valid_trajectory_data()
        if x_coords is None:
            return None
        try:
            # Fit parabola y = ax^2 + bx + c (projectile motion model)
            coefficients = np.polyfit(np.array(x_coords), np.array(y_coords), deg=2)
            return coefficients
        except Exception as e:
            print(f"Error fitting trajectory: {e}")
            return None

    def calculate_apex(self):
        if self.trajectory_coefficients is None:
            return None
        try:
            a, b, c = self.trajectory_coefficients
            # Vertex of parabola: x = -b / 2a
            apex_x = -b / (2 * a)
            apex_y = a * apex_x**2 + b * apex_x + c

            valid_positions = [pos for pos in self.ball_positions if pos is not None]
            if len(valid_positions) > 0:
                start_y       = valid_positions[0][1]
                height_pixels = start_y - apex_y
                height_meters = height_pixels / self.pixels_per_meter
            else:
                height_meters = 0

            return {'x': apex_x, 'y': apex_y, 'height_meters': height_meters}
        except Exception as e:
            print(f"Error calculating apex: {e}")
            return None

    def predict_shot_outcome(self):
        if self.hoop_position is None or self.trajectory_coefficients is None:
            return None
        try:
            a, b, c         = self.trajectory_coefficients
            hoop_x, hoop_y  = self.hoop_position

            # Solve hoop_y = ax^2 + bx + c using quadratic formula
            discriminant = b**2 - 4 * a * (c - hoop_y)

            if discriminant < 0:
                return {
                    'will_make': False, 'confidence': 'high',
                    'reason': 'trajectory_too_low', 'predicted_x': None,
                    'distance_from_center': None
                }

            sqrt_discriminant = np.sqrt(discriminant)
            x1 = (-b + sqrt_discriminant) / (2 * a)
            x2 = (-b - sqrt_discriminant) / (2 * a)
            predicted_x = max(x1, x2)   # Descending arc solution

            distance_pixels = abs(predicted_x - hoop_x)
            distance_meters = distance_pixels / self.pixels_per_meter

            hoop_radius_meters = 0.23
            effective_radius   = hoop_radius_meters * 0.7
            will_make          = distance_meters < effective_radius

            data_points = len([p for p in self.ball_positions if p is not None])
            if data_points < 5:
                confidence = 'low'
            elif data_points < 10:
                confidence = 'medium'
            else:
                confidence = 'high'

            return {
                'will_make': will_make, 'confidence': confidence,
                'reason': 'prediction', 'predicted_x': float(predicted_x),
                'distance_from_center': float(distance_meters),
                'distance_pixels': float(distance_pixels),
                'hoop_radius': float(effective_radius)
            }
        except Exception as e:
            print(f"Error predicting shot outcome: {e}")
            return None

    def calculate_entry_angle(self):
        if self.trajectory_coefficients is None or self.predicted_landing_x is None:
            return None
        try:
            a, b, _ = self.trajectory_coefficients
            x = self.predicted_landing_x
            # Instantaneous slope via derivative: dy/dx = 2ax + b
            slope         = 2 * a * x + b
            angle_degrees = np.degrees(np.arctan2(-slope, 1))
            return angle_degrees
        except Exception as e:
            print(f"Error calculating entry angle: {e}")
            return None

    # ── Shot state machine ─────────────────────────────────────────────
    def detect_shot_start_end(self):
        current_time             = time.time()
        time_since_last_detection = current_time - self.last_detection_time
        ball_detected            = any(pos is not None for pos in list(self.ball_positions)[-3:])

        if ball_detected:
            self.last_detection_time = current_time
            if not self.shot_in_progress:
                self.shot_in_progress = True
                return 'started'
            else:
                return 'in_progress'
        else:
            if self.shot_in_progress and time_since_last_detection > self.shot_timeout:
                self.shot_in_progress = False
                return 'ended'

        return 'no_shot'

    def evaluate_shot_result(self):
        if self.hoop_position is None:
            return 'unknown'

        last_positions    = [pos for pos in list(self.ball_positions)[-10:] if pos is not None]
        if len(last_positions) < 3:
            return 'unknown'

        hoop_x, hoop_y    = self.hoop_position
        hoop_radius_pixels = 0.23 * self.pixels_per_meter

        for pos in last_positions:
            distance = np.sqrt((pos[0] - hoop_x)**2 + (pos[1] - hoop_y)**2)
            if distance < hoop_radius_pixels * 1.5:
                self.made_shots  += 1
                self.total_shots += 1
                self._log_shot('MAKE')
                return 'make'

        self.missed_shots += 1
        self.total_shots  += 1
        self._log_shot('MISS')
        return 'miss'

    def _log_shot(self, result):
        entry = {
            'shot_number': self.total_shots,
            'result':      result,
            'speed':       round(self.current_speed, 1),
            'apex':        round(self.apex_height, 2)  if self.apex_height  else 0.0,
            'entry_angle': round(self.entry_angle, 1)  if self.entry_angle  else 0.0,
            'launch_angle':round(self.launch_angle, 1) if self.launch_angle else 0.0,
        }
        self.shot_log.appendleft(entry)
        socketio.emit('shot_logged', entry)

    # ── Depth estimation (pinhole camera model) ────────────────────────
    def estimate_depth_from_ball_size(self, radius_pixels):
        if radius_pixels <= 0 or not self.depth_calibrated:
            return None
        # depth = (real_diameter * focal_length) / (2 * radius_pixels)
        depth = (self.real_ball_diameter * self.camera_focal_length) / (2 * radius_pixels)
        return depth

    def calibrate_depth_estimation(self, ball_radius_pixels, known_distance_meters):
        if ball_radius_pixels <= 0 or known_distance_meters <= 0:
            print("Invalid calibration values")
            return False
        self.camera_focal_length = (2 * ball_radius_pixels * known_distance_meters) / self.real_ball_diameter
        self.depth_calibrated    = True
        print(f"Depth calibrated. Focal length: {self.camera_focal_length:.1f} px")
        return True

    def screen_to_world_coordinates(self, screen_x, screen_y, depth):
        if depth is None or depth <= 0:
            return None
        offset_x_pixels = screen_x - (self.frame_width  / 2)
        offset_y_pixels = screen_y - (self.frame_height / 2)
        world_x =  (offset_x_pixels * depth) / self.camera_focal_length
        world_y = -(offset_y_pixels * depth) / self.camera_focal_length
        world_z =  depth
        return (world_x, world_y, world_z)

    # ── Automatic hoop detection ───────────────────────────────────────
    def detect_hoop_by_color(self, frame):
        hsv          = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_orange = np.array([5, 100, 100])
        upper_orange = np.array([20, 255, 255])
        mask         = cv2.inRange(hsv, lower_orange, upper_orange)

        kernel = np.ones((5, 5), np.uint8)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) > 0:
            largest_contour = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest_contour) > 500:
                M = cv2.moments(largest_contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    return (cx, cy)
        return None

    def detect_hoop_by_circle(self, frame):
        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray    = cv2.GaussianBlur(gray, (9, 9), 2)
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT,
            dp=1, minDist=100, param1=50, param2=30,
            minRadius=10, maxRadius=100
        )
        if circles is not None:
            circles      = np.uint16(np.around(circles))
            frame_height = frame.shape[0]
            for circle in circles[0, :]:
                x, y, radius = circle
                if y < frame_height * 0.66:
                    return (int(x), int(y))
        return None

    def auto_detect_hoop(self, frame):
        hoop_pos = self.detect_hoop_by_color(frame)
        if hoop_pos:
            self.hoop_position = hoop_pos
            print(f"Hoop detected (color) at: {hoop_pos}")
            return True

        hoop_pos = self.detect_hoop_by_circle(frame)
        if hoop_pos:
            self.hoop_position = hoop_pos
            print(f"Hoop detected (Hough circles) at: {hoop_pos}")
            return True

        print("Auto-detection failed. Use manual selection.")
        return False

    # ── Scale calibration ──────────────────────────────────────────────
    def calculate_scale_from_ground(self):
        if self.hoop_position is None or self.ground_position is None:
            return False

        hx, hy = self.hoop_position
        gx, gy = self.ground_position
        pixel_distance = np.sqrt((hx - gx)**2 + (hy - gy)**2)

        if pixel_distance < 10:
            print("Hoop and ground points too close. Try again.")
            return False

        # pixels_per_meter derived from NBA hoop height: 10 ft = 3.048 m
        self.pixels_per_meter = pixel_distance / self.HOOP_HEIGHT_METERS
        self.scale_calibrated = True
        print(f"Scale calibrated: {self.pixels_per_meter:.2f} px/m")
        return True

    def calculate_distance_from_hoop(self, ball_pos):
        if self.hoop_position is None:
            return None
        pixel_distance = np.sqrt(
            (ball_pos[0] - self.hoop_position[0])**2 +
            (ball_pos[1] - self.hoop_position[1])**2
        )
        return pixel_distance / self.pixels_per_meter

    # ── Frame annotation ───────────────────────────────────────────────
    def draw_info(self, frame, ball_info):

        # Ground marker and calibration line
        if self.ground_position is not None:
            gx, gy = self.ground_position
            cv2.circle(frame, (gx, gy), 8,  (0, 165, 255), -1)
            cv2.circle(frame, (gx, gy), 12, (0, 165, 255),  2)
            cv2.putText(frame, "GROUND", (gx - 30, gy + 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)

            if self.hoop_position is not None:
                cv2.line(frame, (gx, gy), self.hoop_position, (0, 165, 255), 1)
                mid_x = (gx + self.hoop_position[0]) // 2
                mid_y = (gy + self.hoop_position[1]) // 2
                label = "10 ft" if not self.scale_calibrated else f"{self.pixels_per_meter:.0f}px/m"
                cv2.putText(frame, label, (mid_x + 8, mid_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1)

        # Hoop marker
        if self.hoop_position is not None:
            hx, hy = self.hoop_position
            hoop_radius_pixels = int(0.23 * self.pixels_per_meter * 0.7)
            cv2.circle(frame, (hx, hy), hoop_radius_pixels, (0, 255, 0),  1)
            cv2.circle(frame, (hx, hy), 20,                 (0, 255, 100), 2)
            cv2.circle(frame, (hx, hy), 8,                  (0, 255, 0),  -1)
            cv2.circle(frame, (hx, hy), 12,                 (0, 255, 0),   2)
            crosshair_size = 30
            cv2.line(frame, (hx - crosshair_size, hy), (hx + crosshair_size, hy), (0, 255, 0), 2)
            cv2.line(frame, (hx, hy - crosshair_size), (hx, hy + crosshair_size), (0, 255, 0), 2)
            label      = "HOOP"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            label_x    = hx - label_size[0] // 2
            label_y    = hy - 40
            cv2.rectangle(frame,
                          (label_x - 5, label_y - label_size[1] - 5),
                          (label_x + label_size[0] + 5, label_y + 5),
                          (0, 100, 0), -1)
            cv2.putText(frame, label, (label_x, label_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Ball circle and trajectory trail
        if ball_info is not None:
            x, y, radius, depth = ball_info
            cv2.circle(frame, (x, y), radius, (0, 0, 255), 2)
            cv2.circle(frame, (x, y), 2,      (0, 0, 255), -1)

            positions = list(self.ball_positions)[-20:]
            for i in range(1, len(positions)):
                if positions[i-1] is None or positions[i] is None:
                    continue
                cv2.line(frame, positions[i-1], positions[i], (255, 0, 0), 2)

            distance = self.calculate_distance_from_hoop((x, y))
            if distance is not None:
                self.current_distance = distance

            if depth is not None:
                cv2.putText(frame, f"Depth:{depth:.2f}m", (x + 10, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

        # Apex marker
        if self.apex_position is not None:
            apex_x, apex_y = int(self.apex_position[0]), int(self.apex_position[1])
            cv2.drawMarker(frame, (apex_x, apex_y), (0, 255, 255), cv2.MARKER_CROSS, 15, 2)
            cv2.putText(frame, "APEX", (apex_x + 10, apex_y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        # Predicted landing point
        if self.predicted_landing_x is not None and self.hoop_position is not None:
            pred_x = int(self.predicted_landing_x)
            pred_y = int(self.hoop_position[1])
            cv2.drawMarker(frame, (pred_x, pred_y), (255, 0, 255), cv2.MARKER_TRIANGLE_DOWN, 15, 2)

        # Make / miss prediction overlay
        if self.predicted_outcome is not None and self.predicted_outcome.get('will_make') is not None:
            will_make  = self.predicted_outcome['will_make']
            confidence = self.predicted_outcome.get('confidence', 'unknown')
            color      = (0, 255, 0) if will_make else (0, 0, 255)
            text       = f"{'MAKE' if will_make else 'MISS'} ({confidence})"
            cv2.putText(frame, text, (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # FPS and speed readout
        cv2.putText(frame, f"FPS:{self.fps:.1f}",           (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0),    1)
        cv2.putText(frame, f"Speed:{self.current_speed:.1f}m/s", (10, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 1)

        return frame

    # ── Dashboard data payload ─────────────────────────────────────────
    def get_dashboard_data(self):
        trajectory = [{'x': pos[0], 'y': pos[1]} for pos in self.ball_positions if pos is not None]

        return {
            'frame_width':    self.frame_width,
            'frame_height':   self.frame_height,
            'fps':            round(self.fps, 1),
            'frame_latency':  round(self.frame_latency * 1000, 1),
            'detection_time': round(self.detection_time * 1000, 1),
            'draw_time':      round(self.draw_time * 1000, 1),
            'distance':       round(self.current_distance, 2) if self.current_distance else 0,
            'positions_tracked': len([p for p in self.ball_positions if p is not None]),
            'current_speed':  round(self.current_speed, 2),
            'max_speed':      round(self.max_speed, 2),
            'current_angle':  round(self.current_angle, 1),
            'launch_angle':   round(self.launch_angle, 1) if self.launch_angle is not None else 0,
            'total_shots':    self.total_shots,
            'made_shots':     self.made_shots,
            'missed_shots':   self.missed_shots,
            'accuracy':       round((self.made_shots / self.total_shots * 100) if self.total_shots > 0 else 0, 1),
            'trajectory':     trajectory,
            'hoop_position':    list(self.hoop_position)   if self.hoop_position   else None,
            'ground_position':  list(self.ground_position) if self.ground_position else None,
            'scale_calibrated': self.scale_calibrated,
            'pixels_per_meter': round(self.pixels_per_meter, 2),
            'has_prediction':   self.trajectory_coefficients is not None,
            'trajectory_coefficients': list(self.trajectory_coefficients) if self.trajectory_coefficients is not None else None,
            'predicted_outcome':   self.predicted_outcome,
            'predicted_landing_x': round(self.predicted_landing_x, 2) if self.predicted_landing_x else None,
            'apex_position':  list(self.apex_position) if self.apex_position else None,
            'apex_height':    round(self.apex_height, 2) if self.apex_height else None,
            'entry_angle':    round(self.entry_angle, 1) if self.entry_angle else None,
            'shot_in_progress': self.shot_in_progress,
            'shot_log':       list(self.shot_log),
            'depth_calibrated':     self.depth_calibrated,
            'current_depth':        round(self.current_depth, 2) if self.current_depth else None,
            'camera_focal_length':  round(self.camera_focal_length, 1),
        }

    # ── Main processing loop ───────────────────────────────────────────
    def process_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return None

        current_time        = time.time()
        self.frame_latency  = current_time - self.last_frame_time
        self.last_frame_time = current_time
        self.frame_times.append(self.frame_latency)

        if len(self.frame_times) > 0:
            avg_frame_time = sum(self.frame_times) / len(self.frame_times)
            self.fps       = 1.0 / avg_frame_time if avg_frame_time > 0 else 0

        self.frame_count += 1

        detect_start     = time.time()
        ball_info        = self.detect_ball(frame)
        self.detection_time = time.time() - detect_start

        if ball_info is not None:
            x, y, radius, depth = ball_info
            self.ball_positions.append((x, y))
            self.ball_timestamps.append(current_time)

            speed, angle       = self.calculate_speed_and_angle()
            self.current_speed = speed
            self.current_angle = angle

            if speed > self.max_speed:
                self.max_speed = speed

            if len(self.ball_positions) == 3:
                self.launch_angle = self.calculate_launch_angle()
        else:
            self.ball_positions.append(None)
            self.ball_timestamps.append(current_time)

            none_count = sum(1 for p in list(self.ball_positions)[-10:] if p is None)
            if none_count > 7:
                self.launch_angle = None

        draw_start      = time.time()
        display_frame   = self.draw_info(frame, ball_info)
        self.draw_time  = time.time() - draw_start

        # Trajectory regression — runs once 5+ valid points are available
        valid_point_count = len([p for p in self.ball_positions if p is not None])
        if valid_point_count >= 5:
            self.trajectory_coefficients = self.fit_trajectory()

            if self.trajectory_coefficients is not None:
                apex_data = self.calculate_apex()
                if apex_data:
                    self.apex_position = (apex_data['x'], apex_data['y'])
                    self.apex_height   = apex_data['height_meters']

                outcome = self.predict_shot_outcome()
                if outcome:
                    self.predicted_outcome   = outcome
                    self.predicted_landing_x = outcome.get('predicted_x')
                    self.entry_angle         = self.calculate_entry_angle()

        # Shot state machine — evaluates make/miss when shot ends
        shot_status = self.detect_shot_start_end()
        if shot_status == 'ended':
            result = self.evaluate_shot_result()
            print(f"Shot completed: {result.upper()}")
            self.ball_positions.clear()
            self.ball_timestamps.clear()
            self.trajectory_coefficients = None
            self.predicted_outcome       = None

        with self.frame_lock:
            self.current_frame = display_frame.copy()

        return display_frame

    def get_current_frame(self):
        with self.frame_lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        return None

    def run_headless(self):
        print("Basketball Tracker started in web mode")
        print("View dashboard at: http://localhost:8000")

        self.is_running  = True
        last_emit_time   = time.time()

        while self.is_running:
            frame = self.process_frame()
            if frame is None:
                break

            # Emit dashboard data every 5 frames
            if self.frame_count % 5 == 0:
                data = self.get_dashboard_data()
                try:
                    socketio.emit('update', data)
                    if self.frame_count % 150 == 0:
                        current_time = time.time()
                        elapsed      = current_time - last_emit_time
                        print(f"Emitting: FPS={data['fps']:.1f}, Speed={data['current_speed']:.2f}m/s, Tracked={data['positions_tracked']}")
                        last_emit_time = current_time
                except Exception as e:
                    print(f"Error emitting data: {e}")

            time.sleep(0.001)

    def cleanup(self):
        self.is_running = False
        self.cap.release()
        print("Tracker stopped")


# ── Flask routes ───────────────────────────────────────────────────────
tracker = None

def generate_frames():
    global tracker
    frame_skip = 0
    while True:
        if tracker is None:
            time.sleep(0.1)
            continue

        # Send every other frame to reduce bandwidth
        frame_skip += 1
        if frame_skip % 2 != 0:
            time.sleep(0.03)
            continue

        frame = tracker.get_current_frame()
        if frame is None:
            time.sleep(0.01)
            continue

        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.03)

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


# ── SocketIO event handlers ────────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'data': 'Connected'})
    if tracker:
        try:
            emit('update', tracker.get_dashboard_data())
        except Exception as e:
            print(f'Error sending initial data: {e}')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('reset_trajectory')
def handle_reset_trajectory():
    global tracker
    if tracker:
        tracker.ball_positions.clear()
        tracker.ball_timestamps.clear()
        print('Trajectory reset')

@socketio.on('set_ground_position')
def handle_set_ground_position(data):
    global tracker
    if tracker:
        if data.get('x') is not None and data.get('y') is not None:
            tracker.ground_position = (data['x'], data['y'])
            print(f"Ground position set: ({data['x']}, {data['y']})")
            if tracker.hoop_position is not None:
                tracker.calculate_scale_from_ground()
                emit('scale_calibrated', {
                    'pixels_per_meter': round(tracker.pixels_per_meter, 2),
                    'ground_position':  [data['x'], data['y']]
                })
            else:
                emit('ground_set', {'position': [data['x'], data['y']]})
        else:
            tracker.ground_position   = None
            tracker.scale_calibrated  = False
            tracker.pixels_per_meter  = 100
            emit('ground_cleared')

@socketio.on('set_hoop_position')
def handle_set_hoop_position(data):
    global tracker
    if tracker:
        if data['x'] is not None and data['y'] is not None:
            tracker.hoop_position = (data['x'], data['y'])
            print(f"Hoop position set: ({data['x']}, {data['y']})")
            if tracker.ground_position is not None:
                tracker.calculate_scale_from_ground()
                emit('scale_calibrated', {
                    'pixels_per_meter': round(tracker.pixels_per_meter, 2),
                    'hoop_position':    [data['x'], data['y']]
                })
            else:
                emit('hoop_set_success', {'position': [data['x'], data['y']]})
        else:
            tracker.hoop_position = None
            print('Hoop position cleared')
            emit('hoop_cleared')

@socketio.on('auto_detect_hoop')
def handle_auto_detect_hoop():
    global tracker
    if tracker:
        frame = tracker.get_current_frame()
        if frame is not None:
            success = tracker.auto_detect_hoop(frame)
            if success:
                emit('hoop_detected', {
                    'position': list(tracker.hoop_position),
                    'message':  'Hoop automatically detected!'
                })
            else:
                emit('hoop_detection_failed', {
                    'message': 'Could not detect hoop. Please set manually.'
                })
        else:
            emit('hoop_detection_failed', {'message': 'No camera frame available'})

@socketio.on('calibrate_scale_from_ball')
def handle_calibrate_scale_from_ball():
    global tracker
    if tracker:
        if tracker.last_detected_radius and tracker.last_detected_radius > 0:
            # pixels_per_meter from known ball diameter (NBA: 24 cm)
            tracker.pixels_per_meter  = (2 * tracker.last_detected_radius) / tracker.real_ball_diameter
            tracker.scale_calibrated  = True
            print(f"Scale calibrated from ball size: {tracker.pixels_per_meter:.2f} px/m")
            emit('scale_calibrated', {
                'pixels_per_meter': round(tracker.pixels_per_meter, 2),
                'source': 'ball'
            })
        else:
            emit('ball_scale_failed', {'message': 'No ball currently detected in frame'})

@socketio.on('calibrate_depth')
def handle_calibrate_depth(data):
    global tracker
    if tracker:
        radius   = data.get('radius')
        distance = data.get('distance')
        if radius and distance:
            success = tracker.calibrate_depth_estimation(radius, distance)
            if success:
                emit('depth_calibrated', {
                    'focal_length': tracker.camera_focal_length,
                    'message': f'Depth calibrated. Focal length: {tracker.camera_focal_length:.1f}px'
                })
            else:
                emit('calibration_failed', {'message': 'Invalid calibration values'})
        else:
            emit('calibration_failed', {'message': 'Missing radius or distance values'})


# ── Entry point ────────────────────────────────────────────────────────
def run_tracker():
    global tracker
    tracker = BasketballTracker(camera_index=0)
    tracker.run_headless()

if __name__ == "__main__":
    print("\n=== BASKETBALL SHOT TRACKER ===")
    print("Dashboard: http://localhost:8000")
    print("Press Ctrl+C to stop\n")

    tracker_thread = threading.Thread(target=run_tracker, daemon=True)
    tracker_thread.start()

    print("Initializing camera...")
    time.sleep(2)
    print("Camera ready\n")

    socketio.run(app, host='0.0.0.0', port=8000, debug=False, use_reloader=False)
