# Cesium Lab Deployment

## Services

The server eventually runs:

```text
apache2.service
cloudflared.service
postgresql.service
cesium-api.service
```

During frontend development, Vite can additionally run on port `3000`.

## Apache

Apache remains on:

```text
:80
```

Cloudflare Tunnel continues pointing to:

```text
http://localhost:80
```

Apache serves the frontend and proxies API requests.

Conceptually:

```apache
DocumentRoot /path/to/frontend/dist

ProxyPass        /api/ http://127.0.0.1:8000/
ProxyPassReverse /api/ http://127.0.0.1:8000/
```

Therefore:

```text
cesiumlab.net/
    ↓
Apache
    ↓
frontend
```

while:

```text
cesiumlab.net/api/people
    ↓
Apache
    ↓
FastAPI :8000
    ↓
PostgreSQL
```

## API Service

Create:

```text
cesium-api.service
```

which runs approximately:

```text
uvicorn app.main:app
    --host 127.0.0.1
    --port 8000
```

Configure it to:

- start at boot
- restart after failure
- load secrets from `/etc/cesium/api.env`

## Security

Do not expose PostgreSQL directly.

Avoid:

```text
Internet → :5432
```

Use:

```text
Internet
 ↓
Cloudflare
 ↓
Apache
 ↓
FastAPI
 ↓
PostgreSQL
```

## Public vs Private

Eventually consider:

```text
cesiumlab.net
    public

app.cesiumlab.net
    private

api.cesiumlab.net
    private
```

Cloudflare Access can protect the private application and API.

Contact data should not be imported until authentication is working.
