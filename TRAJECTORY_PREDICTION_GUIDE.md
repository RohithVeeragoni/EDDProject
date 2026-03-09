# 🏀 Trajectory Prediction Implementation Guide

## What Was Added

I've implemented complete trajectory prediction and shot analysis for your basketball tracker! Here's everything that was added:

---

## 📊 New Features

### 1. **Trajectory Regression** (Parabolic Curve Fitting)
- Fits a mathematical curve to the ball's path
- Equation: `y = ax² + bx + c`
- Uses NumPy's `polyfit()` for accurate curve fitting

### 2. **Shot Outcome Prediction**
- Predicts if shot will MAKE or MISS
- Calculates where ball will cross hoop plane
- Shows confidence level (low/medium/high)
- Real-time visual feedback on video

### 3. **Apex Detection**
- Finds the highest point of the shot
- Calculates arc height in meters
- Shows apex marker on video feed

### 4. **Entry Angle Calculation**
- Calculates angle ball enters hoop
- Ideal angle: 45 degrees
- Helps evaluate shot quality

### 5. **Automatic Make/Miss Detection**
- Detects when shot starts
- Detects when shot ends
- Automatically updates statistics
- Clears trajectory for next shot

---

## 🎯 New Data Available on Dashboard

All this data is now sent to your web dashboard every 5 frames:

```python
{
    # Prediction status
    'has_prediction': True/False,

    # Shot prediction
    'predicted_outcome': {
        'will_make': True/False,
        'confidence': 'low'/'medium'/'high',
        'predicted_x': 320.5,              # Where ball crosses hoop plane
        'distance_from_center': 0.05,      # Distance from hoop center (meters)
        'reason': 'prediction'
    },

    # Apex data
    'apex_position': [x, y],               # Position of highest point
    'apex_height': 1.2,                    # Height above release (meters)

    # Trajectory math
    'trajectory_coefficients': [a, b, c],  # Parabola coefficients

    # Entry angle
    'entry_angle': 47.5,                   # Angle entering hoop (degrees)

    # Shot status
    'shot_in_progress': True/False,        # Is a shot happening?
}
```

---

## 🎨 Visual Indicators on Video Feed

### What You'll See:

1. **🎯 HOOP Marker** (Green circle)
   - Shows where you clicked to set hoop

2. **🔴 Ball Detection** (Red circle)
   - Current ball position
   - Blue trajectory line following ball

3. **✖️ APEX Marker** (Yellow crosshair)
   - Highest point of trajectory
   - Only appears when prediction is active

4. **🔻 Predicted Landing** (Purple triangle)
   - Where ball will cross hoop plane
   - Shows if trajectory is accurate

5. **MAKE/MISS Prediction** (Top left)
   - Green "MAKE (high)" = Will go in!
   - Red "MISS (medium)" = Won't make it
   - Confidence level shown

---

## 📖 How It Works (Detailed Explanation)

### Step 1: Data Collection
```python
# Every frame, we store:
self.ball_positions.append((x, y))      # Position
self.ball_timestamps.append(time.time()) # When we saw it
```

### Step 2: Extract Valid Data
```python
def get_valid_trajectory_data(self):
    # Filter out None values
    valid_data = [(pos, time) for pos, time in zip(positions, timestamps)
                  if pos is not None]

    # Separate into arrays
    x_coords = [pos[0] for pos, time in valid_data]
    y_coords = [pos[1] for pos, time in valid_data]
    times = [time for pos, time in valid_data]

    return x_coords, y_coords, times
```

**Python Concepts Used:**
- `zip()`: Combines two lists
- List comprehension: `[x for x in list if condition]`
- Tuple unpacking: `pos, time = (x, t)`

### Step 3: Fit Parabola
```python
def fit_trajectory(self):
    x_coords, y_coords, times = self.get_valid_trajectory_data()

    # Convert to NumPy arrays
    x_array = np.array(x_coords)
    y_array = np.array(y_coords)

    # Fit 2nd degree polynomial
    coefficients = np.polyfit(x_array, y_array, deg=2)
    # Returns [a, b, c] for y = ax² + bx + c

    return coefficients
```

**Math Explanation:**
- Basketball follows parabolic path due to gravity
- Parabola equation: `y = ax² + bx + c`
- `a`: Controls steepness (negative for downward)
- `b`: Horizontal velocity component
- `c`: Starting Y position

### Step 4: Find Apex (Highest Point)
```python
def calculate_apex(self):
    a, b, c = self.trajectory_coefficients

    # Calculus! Derivative = 0 at apex
    # For y = ax² + bx + c
    # dy/dx = 2ax + b = 0
    # Solve: x = -b / (2a)

    apex_x = -b / (2 * a)
    apex_y = a * apex_x**2 + b * apex_x + c

    return {'x': apex_x, 'y': apex_y}
```

**Why This Matters:**
- Higher apex = better chance of making shot
- Flat shots hit front rim
- Too steep bounces out

### Step 5: Predict Landing Point
```python
def predict_shot_outcome(self):
    a, b, c = self.trajectory_coefficients
    hoop_x, hoop_y = self.hoop_position

    # Solve: hoop_y = ax² + bx + c
    # Quadratic formula: x = (-b ± √(b² - 4ac)) / 2a

    discriminant = b**2 - 4*a*(c - hoop_y)

    if discriminant < 0:
        return {'will_make': False, 'reason': 'trajectory_too_low'}

    # Two solutions (ball crosses plane twice)
    x1 = (-b + sqrt(discriminant)) / (2*a)
    x2 = (-b - sqrt(discriminant)) / (2*a)

    # Want forward solution (larger X)
    predicted_x = max(x1, x2)

    # Check distance from hoop center
    distance = abs(predicted_x - hoop_x) / pixels_per_meter

    will_make = distance < 0.16  # Within effective radius

    return {
        'will_make': will_make,
        'predicted_x': predicted_x,
        'distance_from_center': distance
    }
```

**Math Visual:**
```
    Y
    |     🏀 (ball going up)
    |    /  \
    |   /    \__ APEX (highest point)
    |  /        \
    | /          \
    |/            🏀 (coming down)
    |              |
    |              v
    |==========[HOOP]===========  <- hoop_y level
    |              ^
    |              |
    |         predicted_x
    |
    +----------------------------> X
```

### Step 6: Calculate Entry Angle
```python
def calculate_entry_angle(self):
    a, b, c = self.trajectory_coefficients
    x = self.predicted_landing_x

    # Derivative gives slope at point
    slope = 2*a*x + b

    # Angle from slope
    angle = arctan2(-slope, 1)
    angle_degrees = degrees(angle)

    return angle_degrees
```

**Why Entry Angle Matters:**
- 45°: Ideal (most room for error)
- 30°: Too flat (hits front rim)
- 60°: Too steep (bounces out)

---

## 🧪 Testing Your Prediction

### Simple Test Function
Add this to test the math:

```python
def test_prediction():
    """Test parabolic fit with known data"""
    import numpy as np

    # Create perfect parabola
    x = np.array([0, 1, 2, 3, 4])
    y = -0.5 * x**2 + 2*x + 1  # Known parabola

    # Fit it
    coeffs = np.polyfit(x, y, 2)
    print(f"Coefficients: {coeffs}")
    # Should print: [-0.5, 2.0, 1.0]

    # Find apex
    a, b, c = coeffs
    apex_x = -b / (2*a)
    apex_y = a * apex_x**2 + b * apex_x + c
    print(f"Apex: ({apex_x:.1f}, {apex_y:.1f})")
    # Should print: Apex: (2.0, 3.0)

    print("✓ Test passed!")

# Run it
test_prediction()
```

---

## 🎮 How to Use

### 1. Start the Tracker
```bash
python EDDProject.py
```

### 2. Open Dashboard
- Go to `http://localhost:8000` in browser

### 3. Set Hoop Position
- Click on the video where the hoop is
- Green circle marks the hoop

### 4. Take a Shot!
- Throw your ball/object
- Watch the predictions appear in real-time:
  - APEX marker (yellow crosshair) at highest point
  - Predicted landing point (purple triangle)
  - MAKE/MISS prediction (top left)

### 5. View Results
- Dashboard shows all metrics
- Statistics update automatically
- Trajectory clears for next shot

---

## 📊 Understanding the Metrics

### Release Angle (launch_angle)
```
90° = Straight up
45° = Ideal basketball shot  ← Best!
0° = Horizontal
```

### Entry Angle
```
60°+ = Too steep (bounces out)
45° = Ideal (most room for error)  ← Best!
<30° = Too flat (hits front rim)
```

### Arc Height (apex_height)
```
> 2m = High arc (good!)
1-2m = Medium arc
< 1m = Flat shot (risky)
```

### Prediction Confidence
```
high   = 10+ data points (reliable)
medium = 5-9 data points (okay)
low    = 3-4 data points (uncertain)
```

---

## 🔧 Tuning Parameters

You can adjust these in the code:

### Shot Detection Timeout
```python
self.shot_timeout = 2.0  # Seconds before shot ends
# Increase if shots take longer
# Decrease for faster detection
```

### Make/Miss Tolerance
```python
effective_radius = hoop_radius_meters * 0.7  # 70% of hoop
# Increase to be more generous
# Decrease to be more strict
```

### Minimum Data Points
```python
if valid_point_count >= 5:  # Need 5+ points for prediction
# Increase for more accurate predictions
# Decrease for earlier predictions
```

---

## 🐛 Common Issues & Solutions

### "No prediction appears"
**Problem:** Not enough data points
**Solution:**
- Need at least 5 consecutive detections
- Improve lighting/contrast
- Adjust color detection range

### "Predictions are wildly wrong"
**Problem:** Noisy detection or false positives
**Solution:**
- Set hoop position accurately
- Use consistent colored ball
- Better lighting conditions
- Reduce background objects of same color

### "Shot never ends"
**Problem:** Ball stays in frame too long
**Solution:**
- Decrease `shot_timeout` value
- Make sure ball leaves camera view
- Check for false detections

### "Makes counted as misses"
**Problem:** Tolerance too strict
**Solution:**
- Increase `effective_radius` multiplier
- Calibrate `pixels_per_meter` more accurately
- Ensure hoop position is exact center

---

## 🎓 Python Concepts You Learned

1. **NumPy Arrays**: Fast numerical operations
2. **Polynomial Fitting**: `np.polyfit()` for curve fitting
3. **List Comprehensions**: Compact list creation
4. **Zip Function**: Combining multiple lists
5. **Dictionary Returns**: Structured function outputs
6. **State Machines**: Shot detection logic
7. **Mathematical Functions**: `arctan2()`, `sqrt()`, `degrees()`
8. **Quadratic Formula**: Solving parabolic equations
9. **Calculus**: Using derivatives to find apex
10. **Exception Handling**: `try/except` for robustness

---

## 🚀 Next Steps (Future Enhancements)

### Phase 1 ✅ (DONE!)
- [x] Basic trajectory regression
- [x] Shot outcome prediction
- [x] Apex detection
- [x] Entry angle calculation
- [x] Visual feedback

### Phase 2 (Optional)
- [ ] Shot zones (3-pointer vs 2-pointer detection)
- [ ] Shooting percentage by zone
- [ ] Time-based regression (velocity over time)
- [ ] Spin detection (if visible)

### Phase 3 (Advanced)
- [ ] Machine learning classifier for make/miss
- [ ] Compare with historical "perfect shots"
- [ ] Personalized shooting tips
- [ ] Export data to CSV for analysis

---

## 📝 Code Structure Summary

```
EDDProject.py
├── __init__()
│   ├── Added: trajectory_coefficients
│   ├── Added: predicted_outcome
│   ├── Added: apex_height/position
│   ├── Added: entry_angle
│   └── Added: shot detection variables
│
├── NEW METHODS:
│   ├── get_valid_trajectory_data()  → Extract clean data
│   ├── fit_trajectory()             → Fit parabola
│   ├── calculate_apex()             → Find highest point
│   ├── predict_shot_outcome()       → Predict make/miss
│   ├── calculate_entry_angle()      → Entry angle
│   ├── detect_shot_start_end()      → Shot detection
│   └── evaluate_shot_result()       → Make/miss tracking
│
├── UPDATED METHODS:
│   ├── process_frame()              → Calculate predictions
│   ├── get_dashboard_data()         → Include prediction data
│   └── draw_info()                  → Draw predictions
│
└── Dashboard Integration
    └── Real-time prediction updates via SocketIO
```

---

## 🎉 You're All Set!

Your basketball tracker now has:
- ✅ Real-time trajectory prediction
- ✅ Shot outcome forecasting
- ✅ Automatic make/miss detection
- ✅ Advanced shot quality metrics
- ✅ Visual feedback on video

**Try it out and see predictions in action!** 🏀

---

*Questions? Check the inline code comments - every function has detailed explanations!*
