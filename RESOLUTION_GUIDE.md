# 📹 Camera Resolution Guide

## Current Setting: 720p HD (1280x720) ✓

Your tracker is now set to **1280x720 (720p HD)** - the recommended balance of quality and performance.

---

## 🎯 Resolution Options

Edit [EDDProject.py](EDDProject.py) lines 23-24 to change resolution:

### Option 1: VGA - 640x480 (Fast)
```python
self.frame_width = 640
self.frame_height = 480
```
**Pros:**
- Fastest processing
- Lowest CPU usage
- Best for older computers

**Cons:**
- Lower image quality
- Ball harder to detect at distance
- Less accurate tracking

**Use when:** Performance is more important than quality

---

### Option 2: 720p HD - 1280x720 (Balanced) ✓ RECOMMENDED
```python
self.frame_width = 1280
self.frame_height = 720
```
**Pros:**
- Good image quality
- 2x better than VGA
- Still runs smoothly (~25-30 FPS)
- Better ball detection at distance

**Cons:**
- Slightly higher CPU usage than VGA
- Not the absolute highest quality

**Use when:** You want the best balance (default choice)

---

### Option 3: 1080p Full HD - 1920x1080 (Best Quality)
```python
self.frame_width = 1920
self.frame_height = 1080
```
**Pros:**
- Best image quality
- Most accurate ball detection
- Excellent for 15+ foot distances
- Professional-looking output

**Cons:**
- Higher CPU usage
- May reduce FPS to 15-20
- Requires better computer

**Use when:** You have a powerful computer and want maximum quality

---

### Option 4: 4K - 3840x2160 (Maximum)
```python
self.frame_width = 3840
self.frame_height = 2160
```
**Pros:**
- Ultimate quality
- Best for very long distances

**Cons:**
- Very high CPU usage
- FPS may drop to 5-10
- Only if camera supports it
- Not recommended for real-time tracking

**Use when:** Recording for post-processing (not real-time)

---

## 🚀 How to Change Resolution

**Step 1:** Open [EDDProject.py](EDDProject.py)

**Step 2:** Find lines 23-24:
```python
self.frame_width = 1280
self.frame_height = 720
```

**Step 3:** Change to your desired resolution:
```python
# For 1080p:
self.frame_width = 1920
self.frame_height = 1080
```

**Step 4:** Save and restart:
```bash
python EDDProject.py
```

**Done!** The dashboard will automatically adapt to the new resolution.

---

## 📊 Performance Comparison

| Resolution | Quality | FPS | CPU | Best For |
|------------|---------|-----|-----|----------|
| 640x480 | ⭐⭐ | ~30 | Low | Old computers |
| 1280x720 | ⭐⭐⭐⭐ | ~25-30 | Medium | **Recommended** |
| 1920x1080 | ⭐⭐⭐⭐⭐ | ~15-20 | High | Powerful PCs |
| 3840x2160 | ⭐⭐⭐⭐⭐ | ~5-10 | Very High | Post-processing |

---

## 💡 Tips for Best Results

### For 15-Feet Behind 3-Point Line Setup
**Recommended:** 1280x720 or 1920x1080
- Ball will be smaller at that distance
- Higher resolution helps detect smaller objects
- 720p is usually sufficient
- 1080p if you have CPU headroom

### Check If Your Camera Supports It
Not all cameras support all resolutions. To check:
```bash
python EDDProject.py
```

Look for console output showing actual camera resolution:
```
Camera initialized at: 1280x720
```

If it says something different (like `640x480`), your camera doesn't support that resolution.

### Performance Troubleshooting

**If FPS is too low:**
1. Lower the resolution
2. Close other programs
3. Use 640x480 for testing

**If tracking is poor at distance:**
1. Increase resolution to 720p or 1080p
2. Move camera closer
3. Use brighter lighting

---

## 🔍 What Changed in Your Code

### 1. Dynamic Resolution Variables
```python
# Before (hardcoded):
self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# After (configurable):
self.frame_width = 1280
self.frame_height = 720
self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
```

### 2. Auto-Scaling Dashboard
The dashboard now automatically receives the camera resolution from the server and scales everything correctly. No manual adjustments needed!

### 3. Updated Methods
- `screen_to_world_coordinates()` - Uses dynamic dimensions
- `get_dashboard_data()` - Sends resolution to dashboard
- JavaScript canvas scaling - Adapts to any resolution

---

## 🎬 Example Configurations

### For Engineering Class Demo
```python
self.frame_width = 1280
self.frame_height = 720
```
Good quality, smooth performance, looks professional.

### For Final Presentation Video
```python
self.frame_width = 1920
self.frame_height = 1080
```
Best quality for recording. Record video, then show to class.

### For Quick Testing at Home
```python
self.frame_width = 640
self.frame_height = 480
```
Fast iteration when developing features.

---

## 📝 Common Resolutions Reference

| Name | Resolution | Aspect Ratio | Notes |
|------|------------|--------------|-------|
| QVGA | 320x240 | 4:3 | Too low for tracking |
| VGA | 640x480 | 4:3 | Minimum for tracking |
| SVGA | 800x600 | 4:3 | Rarely supported |
| HD | 1280x720 | 16:9 | **Best balance** |
| Full HD | 1920x1080 | 16:9 | Professional quality |
| 2K | 2048x1080 | 19:10 | Cinema format |
| 4K UHD | 3840x2160 | 16:9 | Overkill for real-time |

---

## 🎯 Quick Recommendation

**Just want it to work great?**
Keep it at **1280x720** (current setting) ✓

**Need maximum quality?**
Try **1920x1080** (if your computer can handle it)

**Having performance issues?**
Drop to **640x480** (temporary for testing)

---

## 🔧 Troubleshooting

### "Camera shows wrong resolution"
Your camera doesn't support the requested resolution. It automatically falls back to the closest supported resolution. Check console output for actual resolution.

### "Everything looks squished"
Dashboard should auto-scale, but if not, try:
1. Refresh the browser
2. Clear browser cache
3. Restart the tracker

### "FPS dropped significantly"
Higher resolution = more processing. Either:
1. Lower the resolution
2. Upgrade computer
3. Close other programs

---

**Current Resolution:** 1280x720 (720p HD)
**Expected FPS:** 25-30
**Status:** Optimized for quality and performance ✓
