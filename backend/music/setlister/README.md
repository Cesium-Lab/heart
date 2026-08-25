# Setlister environment configuration

The Setlister music service uses an API key and runtime settings from environment variables. Secrets belong in the backend only; never place them in the Astro frontend under `mr-ray-apache2`.

## Required variables

Copy the committed template when setting up local development:

```bash
cp backend/music/setlister/.env.example backend/music/setlister/.env
```

Then edit `.env` and provide the real key:

```dotenv
GETSONGBPM_API_KEY=replace-with-your-real-key
SETLISTER_PORT=5000
SETLISTER_API_TIMEOUT=10
SETLISTER_CACHE_TTL=3600
SETLISTER_RATE_LIMIT=60
```

- `GETSONGBPM_API_KEY` authenticates requests to GetSongBPM.
- `SETLISTER_PORT` selects the local service port.
- `SETLISTER_API_TIMEOUT` limits how long an upstream request may take, in seconds.
- `SETLISTER_CACHE_TTL` controls cached-result lifetime, in seconds.
- `SETLISTER_RATE_LIMIT` controls the service request limit.

## Local development

Store real local values in:

```text
backend/music/setlister/.env
```

This file is ignored by Git. Confirm that it remains untracked before committing:

```bash
git check-ignore backend/music/setlister/.env
```

Commit `.env.example`, but never commit `.env` or paste its contents into logs, issues, or frontend code.

## Production

Keep production secrets outside the repository in `/etc/cesium/music.env`:

```bash
sudo install -d -m 0750 -o root -g cskin /etc/cesium
sudo install -m 0640 -o root -g cskin backend/music/setlister/.env /etc/cesium/music.env
```

These ownership settings allow a systemd service running as `cskin` to read the file without making it world-readable. If the service runs as another account, replace the group with that account or its dedicated service group.

Reference the file from the service unit:

```ini
[Service]
User=cskin
EnvironmentFile=/etc/cesium/music.env
```

After adding or changing `EnvironmentFile` in the unit:

```bash
sudo systemctl daemon-reload
sudo systemctl restart setlister.service
sudo systemctl status setlister.service
```

Changing only a value inside `/etc/cesium/music.env` requires a restart, but not `daemon-reload`:

```bash
sudo systemctl restart setlister.service
```

## Rotating the API key

1. Generate or obtain a replacement key from the provider.
2. Update the local `.env` if local development uses the same key.
3. Update `/etc/cesium/music.env` on the production server.
4. Restart `setlister.service`.
5. Verify the service, then revoke the old key.

Do not print the key during verification. Check service health or make a normal application request instead.

## Astro warning

Never use `GETSONGBPM_API_KEY` in `mr-ray-apache2`, browser JavaScript, or an Astro variable whose name begins with `PUBLIC_`. Astro exposes `PUBLIC_*` values to browser code. The frontend should call the backend, and the backend should attach the private API key when contacting the music provider.
