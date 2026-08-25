# Setlister environment configuration

Setlister is a backend service and belongs in `backend/music/setlister/`. It is not copied into `frontend/dist`. Apache exposes `/api/setlister/` by proxying to `http://127.0.0.1:5702/api/setlister/`.

## Migration status

The configuration files have moved here, but the application is not yet fully migrated:

- `server.py` is missing from this directory and is not tracked by Git.
- `deploy/systemd/setlister.service` does not exist yet.
- the installed `/etc/systemd/system/setlister.service` still names the removed `mr-ray-apache2/music/setlister` path.
- the currently running process remains healthy only because it started before that directory was moved.

Do not restart the service or reboot expecting it to recover until `server.py` is restored and a corrected tracked unit is added. `scripts/deploy-startup.sh` can detect and check an installed Setlister unit, but it cannot install the missing application or unit.

## Local configuration

```bash
cp backend/music/setlister/.env.example backend/music/setlister/.env
```

Use port `5702` to match Apache:

```dotenv
GETSONGBPM_API_KEY=replace-with-your-real-key
SETLISTER_PORT=5702
SETLISTER_API_TIMEOUT=10
SETLISTER_CACHE_TTL=3600
SETLISTER_RATE_LIMIT=60
```

Confirm that the secret file remains untracked:

```bash
git check-ignore backend/music/setlister/.env
```

Never commit `.env`, print it in logs, or copy its values into `frontend/` or an Astro variable beginning with `PUBLIC_`.

## Intended production configuration

Store production secrets outside the repository:

```bash
sudo install -d -m 0750 -o root -g cskin /etc/cesium
sudo install -m 0640 -o root -g cskin backend/music/setlister/.env /etc/cesium/music.env
```

The future tracked unit should use:

```ini
[Service]
User=cskin
WorkingDirectory=/home/cskin/Cesium/heart/backend/music/setlister
EnvironmentFile=/etc/cesium/music.env
ExecStart=/home/cskin/Cesium/heart/.venv/bin/python server.py
```

Once `server.py` and `deploy/systemd/setlister.service` are restored, add that unit to `scripts/deploy-startup.sh`, rerun the helper, and verify:

```bash
systemctl status setlister.service --no-pager
curl --fail http://127.0.0.1:5702/api/setlister/health
```
