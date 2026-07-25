# Basketball Shot Tracker

Real-time basketball shot tracking system built with Python and OpenCV. A colored ball is tracked through a Limelight 3A camera, its trajectory is modeled as a parabola using polynomial regression, and the system predicts whether the shot will go in before the ball reaches the hoop. Everything streams live to a web dashboard running on a Raspberry Pi 4B.

---

## Hardware

- **Raspberry Pi 4B** — runs the Python tracking script and hosts the Flask web server
- **Limelight 3A** — networked camera that streams MJPEG video to the Pi over a local network connection
- **10000mAh power bank** — powers the Pi and Limelight in the field without needing a wall outlet

---

## Requirements

- Python 3.7+
- OpenCV (`cv2`)
- NumPy
- Flask
- Flask-SocketIO

```
pip install -r requirements.txt
```

---

## How to Run

```
python EDDProject.py
```

Open a browser to `http://localhost:5000`, or from another device on the same network use the Pi's IP address instead of localhost.

---

## Camera Setup

On startup the system tries to connect to the Limelight 3A over the local network, checking these URLs in order:

- `http://limelight.local:5800/stream.mjpeg`
- `http://limelight.local:5800`
- `http://limelight.local:5801/stream.mjpeg`
- `http://limelight.local:5801`

It reads a test frame from each and moves on if nothing comes back. If all four fail, it falls back to the default webcam at index 0. The Limelight 3A streams at 1280x960; the webcam fallback runs at 1280x720.

---

## Ball Detection

The ball is isolated per frame using HSV color filtering. HSV is used instead of RGB because it separates color (hue) from brightness, which makes the detection much more stable under different lighting. The current range targets a rose-pink ball:

- Lower: `[140, 40, 40]`
- Upper: `[180, 255, 255]`

The Limelight tends to output desaturated video, so the saturation channel of each frame gets multiplied by 1.6 and clipped to 255 before the mask is applied. This recovers color information that would otherwise push the ball outside the detection range.

After masking, a 2x2 morphological opening (erosion then dilation) removes pixel-level noise without destroying the blob that represents a fast-moving ball. The system then finds contours in the mask and checks the top 3 by area. Rather than always picking the largest, it prefers whichever contour's centroid falls closest to the position the ball was predicted to be at based on its last known velocity. This matters when background objects partially enter the color range — without the velocity check, the system might lock onto the wrong blob.

### Predictive Gap-Filling

When detection fails (motion blur, occlusion, the ball moving too fast for the exposure), the system doesn't immediately drop the trajectory. Instead it extrapolates forward using the velocity vector computed from the last two detected positions:

```
predicted_x = last_x + velocity_x
predicted_y = last_y + velocity_y
```

This fills up to 5 consecutive missed frames before the tracker resets. At 30 FPS that covers roughly 160ms of lost signal, which is enough to bridge most motion blur events.

---

## Trajectory Regression

Once at least 5 valid positions are collected, the system fits a second-degree polynomial to them using `numpy.polyfit`. This gives three coefficients `[a, b, c]` that define the parabola:

```
y = ax² + bx + c
```

This works because a basketball in free flight follows a parabolic path — it's a projectile under constant gravitational acceleration, so height as a function of horizontal position is exactly a quadratic. The regression finds the least-squares best fit to all collected points, which smooths out detection noise.

Note that in image coordinates, Y increases downward. So a ball going up has a negative vertical velocity in world terms but a decreasing pixel Y value. The parabola's `a` coefficient will be positive in pixel space (the curve opens downward in real space but upward when Y is flipped). This matters when interpreting signs in the derivative calculations below.

---

## Apex Calculation

The apex is the vertex of the fitted parabola — the point where vertical velocity is zero and the ball transitions from rising to falling. To find it, take the derivative of the parabola and set it equal to zero:

```
y  = ax² + bx + c
dy/dx = 2ax + b = 0
x_apex = -b / (2a)
```

Then plug `x_apex` back into the original equation to get `y_apex`. The height of the apex above the release point is computed by subtracting `y_apex` from the Y coordinate of the first detected position (again, accounting for the inverted Y axis). That pixel difference is then divided by `pixels_per_meter` to get meters.

---

## Shot Prediction

To predict whether a shot will go in, the system solves for where the parabola intersects the hoop's Y coordinate in pixel space. The hoop's Y position is known from either a manual click or auto-detection. Setting `y = hoop_y` in the parabola equation gives:

```
hoop_y = ax² + bx + c
ax² + bx + (c - hoop_y) = 0
```

This is a standard quadratic. Applying the quadratic formula:

```
discriminant = b² - 4a(c - hoop_y)
x = (-b ± √discriminant) / (2a)
```

If the discriminant is negative, the parabola never reaches the hoop's height — the ball falls short, automatic miss. Otherwise there are two solutions (the ball crosses the hoop's horizontal plane twice: once on the way up, once on the way down). The system takes the larger X value, which corresponds to the descending crossing — the one that actually matters for scoring.

The predicted landing X is then compared to the hoop's X coordinate. The difference in pixels is converted to meters, and if it falls within the effective hoop radius (0.23m * 0.7, so about 70% of the physical rim radius to account for imprecise pixel coordinates), the shot is predicted as a make.

Confidence is tied to how many data points went into the regression: low for 3-4 points, medium for 5-9, high for 10 or more.

---

## Entry Angle

The entry angle is the angle at which the ball is descending as it crosses the hoop plane. It's computed from the derivative of the parabola at `x = predicted_landing_x`:

```
slope = dy/dx at landing = 2a * x_landing + b
angle = arctan(-slope, 1)
```

The slope is negated before taking the arctangent because of the inverted Y axis — a negative slope in pixel space means the ball is moving downward in real life, which is the correct descent direction. The angle is returned in degrees. An entry angle around 45 degrees is generally considered ideal in basketball because it maximizes the effective opening of the hoop from the ball's perspective.

---

## Launch Angle

The launch angle is calculated from the first three detected positions at the beginning of a shot. The vector from position 1 to position 3 gives the initial direction of travel:

```
dx = x3 - x1
dy = y3 - y1
angle = arctan2(-dy, dx)
```

Again, `dy` is negated to account for the flipped Y axis so that an upward-moving ball produces a positive angle. This is a simpler estimate than the regression-based angle since it only uses early trajectory data, but it's useful for comparing shot form across attempts.

---

## Speed Calculation

Speed is computed from the two most recent detected positions and the time elapsed between them:

```
pixel_distance = sqrt((x2 - x1)² + (y2 - y1)²)
meter_distance = pixel_distance / pixels_per_meter
speed = meter_distance / time_delta
```

The result is in meters per second. This is a frame-by-frame instantaneous speed, not an average, so it fluctuates with detection jitter. The dashboard also tracks the maximum speed seen across the current shot.

---

## Depth Estimation

The distance from the camera to the ball is estimated using the pinhole camera model. The underlying idea is similar triangles: an object of known real-world size will project to a larger image when close and a smaller image when far, and the relationship is linear.

For a camera with focal length `f` (in pixels), a real object of diameter `D` at distance `d` will appear as a circle of radius `r` in the image:

```
r / f = (D/2) / d
d = (D * f) / (2 * r)
```

With the real basketball diameter fixed at 0.24m:

```
depth = (0.24 * focal_length) / (2 * radius_pixels)
```

The default focal length is 800 pixels, which is a rough estimate. It can be calibrated by placing the ball at a measured distance and using the calibration panel — the system back-solves for `f` using the same formula rearranged:

```
focal_length = (2 * radius_pixels * known_distance) / 0.24
```

---

## World Coordinate Conversion

Once depth is known, any pixel coordinate can be mapped to a 3D real-world position. The screen center is treated as the optical axis of the camera:

```
offset_x = screen_x - (frame_width / 2)
offset_y = screen_y - (frame_height / 2)

world_x =  (offset_x * depth) / focal_length
world_y = -(offset_y * depth) / focal_length
world_z =  depth
```

This is again just similar triangles. The negative sign on `world_y` flips the screen's Y axis back to a right-handed coordinate system where positive Y is up.

---

## Scale Calibration

All real-world distance measurements depend on `pixels_per_meter`. There are two ways to establish this:

**Hoop + Ground markers** — The user clicks the center of the hoop and a point on the floor directly below it. The Euclidean pixel distance between those two points is calculated, then divided by the known hoop height (3.048m, the NBA standard of 10 feet):

```
pixels_per_meter = pixel_distance(hoop, ground) / 3.048
```

**Ball size** — If the ball is currently visible, its detected pixel radius combined with the known real diameter (0.24m) gives:

```
pixels_per_meter = (2 * radius_pixels) / 0.24
```

This method is less accurate because ball detection radius varies with distance and detection noise, but it works when a physical reference point isn't available.

---

## Shot Detection

A four-state machine tracks each shot: `no_shot` → `started` → `in_progress` → `ended`. A shot ends when no ball is detected for 2 continuous seconds (`shot_timeout = 2.0`). When the shot ends, `evaluate_shot_result` checks the last few tracked positions against the hoop radius (0.23m in pixels). If any of them fall within that radius the shot is logged as a make, otherwise a miss. The result, along with speed, apex height, entry angle, and launch angle, gets stored in a deque of up to 50 entries and pushed to the dashboard via the `shot_logged` SocketIO event.

---

## Hoop Auto-Detection

When the user clicks Auto-Detect, the system tries two methods in sequence:

1. **Color detection** — Masks for the orange color of a basketball rim (HSV hue 5-20, saturation and value both above 100), finds contours, and returns the centroid of the largest match.

2. **Hough Circle Transform** — Applies Canny edge detection to a grayscale version of the frame and runs `cv2.HoughCircles` to find circular shapes. Only circles in the upper two-thirds of the frame are accepted, since the hoop is never near the floor.

If both fail, the system returns a `hoop_detection_failed` event and the user falls back to clicking manually.

---

## Flask Routes

- `GET /` — Serves the dashboard
- `GET /video_feed` — MJPEG stream, every other frame at JPEG quality 70 to keep bandwidth manageable

---

## SocketIO Events

**Client to server:**

| Event | What it does |
|-------|-------------|
| `reset_trajectory` | Clears all stored ball positions and timestamps |
| `set_hoop_position` | Sets the hoop marker; triggers scale calibration if ground is set |
| `set_ground_position` | Sets the ground marker; triggers scale calibration if hoop is set |
| `auto_detect_hoop` | Runs hoop detection (color then Hough), emits result event |
| `calibrate_scale_from_ball` | Uses current detected ball radius to compute pixels_per_meter |
| `calibrate_depth` | Calibrates focal length given ball radius and known distance |

**Server to client:**

| Event | What it carries |
|-------|-------------|
| `update` | Full data packet every 5 frames: FPS, speed, angles, stats, prediction, calibration state |
| `shot_logged` | Shot result with speed, apex, entry angle, launch angle |
| `hoop_detected` | Auto-detect success with pixel position |
| `hoop_detection_failed` | Auto-detect could not find the rim |
| `scale_calibrated` | Confirmed pixels_per_meter value |
| `depth_calibrated` | Confirmed focal length value |
| `hoop_set_success / ground_set / hoop_cleared / ground_cleared` | Marker state confirmations |

---

## Dashboard

Single-page HTML/JS interface connected to the server via Socket.IO. Everything updates on the `update` event without a page reload.

**Live Feed** — Camera stream with a transparent overlay canvas. Clicking the video in hoop or ground mode emits the coordinate to the server (scaled from display pixels back to camera resolution). Buttons: Set Hoop, Set Ground, Auto-Detect, Clear, Reset.

**Ball Trajectory** — Canvas that redraws every update. Renders the arc as an orange-to-cyan gradient line with the hoop as a glowing green circle. Scales all pixel coordinates to fit the canvas dimensions.

**Shot Prediction** — MAKE / MISS / WAITING in large text with confidence level. Below that: apex height, entry angle, launch angle, and current speed.

**Session Stats** — Total shots, made, missed, accuracy percentage.

**Calibration Panel** — Three subsections covering hoop+ground calibration, ball size calibration, and depth calibration. Each shows its current status and updates after a successful calibration event from the server.

**System Status** — Live badges for FPS, tracked position count, depth, distance to hoop, frame latency, detection time, scale (px/m), and focal length.

**Shot Log** — Table of the last 50 shots: result (green/red), speed, max speed, apex height, entry angle, launch angle. Each new row highlights for 2 seconds when it appears.

---

## Project Structure

```
EDDProject.py
basketball-tracker/
    templates/
        dashboard.html
requirements.txt
```
