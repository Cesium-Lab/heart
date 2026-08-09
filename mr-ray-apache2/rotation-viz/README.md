# Rotation Visualizer

## Files
- `rotation-visualizer.html` → serve statically via Apache
- `app.py` → Flask backend (port 5001)
- `requirements.txt` → Python deps

## Deploy to mr-ray

```bash
# 1. Copy files
sudo mkdir -p /var/www/html/rotation-viz
sudo cp rotation-visualizer.html /var/www/html/rotation-viz/
sudo cp app.py requirements.txt /var/www/html/rotation-viz/

# 2. Install deps
pip3 install -r requirements.txt --break-system-packages

# 3. Test backend manually first
cd /var/www/html/rotation-viz && python3 app.py

# 4. Install as systemd service (optional, for persistence)
sudo cp rotation-viz.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rotation-viz
sudo systemctl start rotation-viz

# 5. Check it's running
curl http://localhost:5001/api/health
```

## Link from another HTML page

```html
<a href="/rotation-viz/rotation-visualizer.html">Rotation Visualizer</a>
```

## Apache config note

The HTML file calls the Flask API at `http://localhost:5001`.
Since the HTML is loaded from mr-ray and the API runs on mr-ray, this works.

If you want to expose the API through Apache instead (cleaner URLs, no CORS issues):
```apache
# Add to your VirtualHost in /etc/apache2/sites-enabled/
ProxyPass /api/ http://localhost:5001/api/
ProxyPassReverse /api/ http://localhost:5001/api/
```
Then change `API_BASE` in the HTML from `http://localhost:5001` to `` (empty string).
Requires: `sudo a2enmod proxy proxy_http && sudo systemctl restart apache2`

## Features
- Input: quaternion (scalar-first or scalar-last), rotation matrix, Euler angles (ZYX/XYZ), axis-angle
- Output: all representations simultaneously
- 3D visualization with draggable orbit camera
- Gimbal lock detection
- SO(3) validity check (orthonormality + det=1)
- Presets: identity, Rx/Ry/Rz 90°, gimbal lock demo
- Reference panel with Rodrigues formula, quaternion math, Euler caveats