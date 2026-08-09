# SETLISTER.EXE

A local-first song library and setlist builder. Song libraries remain in browser storage and can be imported/exported as JSON. The optional Python service securely proxies song searches to GetSongBPM so the API key never reaches the browser.

## 1. Get a GetSongBPM API key

Register at <https://getsongbpm.com/api>. GetSongBPM requires a backlink; the Setlister footer already includes one.

## 2. Create the environment file

From this directory:

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and replace the placeholder:

```dotenv
GETSONGBPM_API_KEY=your_real_key_here
SETLISTER_PORT=5702
```

Never commit `.env`. The repository `.gitignore` excludes it.

## 3. Install and test locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
```

In another terminal:

```bash
curl http://127.0.0.1:5702/api/setlister/health
curl 'http://127.0.0.1:5702/api/setlister/search?title=Master%20of%20Puppets&artist=Metallica'
```

The health response should contain `"configured": true`. The server listens only on loopback because Apache should be the public entry point.

## 4. Configure Apache

Enable the proxy module once:

```bash
sudo a2enmod proxy proxy_http
```

Add these lines inside the applicable Apache `VirtualHost`:

```apache
ProxyPass        /api/setlister/ http://127.0.0.1:5702/api/setlister/
ProxyPassReverse /api/setlister/ http://127.0.0.1:5702/api/setlister/
```

If a broader `ProxyPass /api/ ...` rule exists, put the Setlister rule before it. Then validate and reload:

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

Open `/music/setlister/`. The **Find song data** button calls `/api/setlister/search`; the secret stays in the Python process.

## 5. Run at startup with systemd (optional)

The included unit assumes this directory is deployed at `/var/www/html/music/setlister` and its virtual environment is `.venv`:

```bash
sudo cp setlister.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now setlister
sudo systemctl status setlister
```

If the project lives elsewhere, update `WorkingDirectory`, `EnvironmentFile`, and `ExecStart` before installing the unit.

## Environment settings

| Variable | Default | Purpose |
|---|---:|---|
| `GETSONGBPM_API_KEY` | required | Server-only GetSongBPM credential |
| `SETLISTER_PORT` | `5702` | Loopback service port |
| `SETLISTER_API_TIMEOUT` | `8` | Upstream timeout in seconds |
| `SETLISTER_CACHE_TTL` | `3600` | Search cache lifetime in seconds |
| `SETLISTER_RATE_LIMIT` | `60` | Total searches allowed per minute |

## Data and security

- The API key is sent to GetSongBPM in an HTTP header and is never returned to the browser.
- Search results are cached in memory to reduce upstream API usage.
- The proxy applies a global per-minute rate limit to protect the API allowance.
- Song libraries and setlists stay in `localStorage` until downloaded as JSON.
- GetSongBPM values are starting points; live arrangements may use different keys or tempos.
