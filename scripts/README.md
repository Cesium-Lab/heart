# Scripts

- `./scripts/publish.sh`: rebuild the site and put it live (no sudo, ~10 s). Use this after
  frontend edits. `--fresh` also reinstalls npm packages.
- `./scripts/lint.sh`: the same checks as CI (ruff, shellcheck, Prettier) before you push.
  `--fix` auto-fixes formatting and simple lint issues. Uses the root `.venv` (tools pinned in
  `requirements.txt`).
- `.venv/bin/python scripts/make_icons.py`: rebuild favicons, section icons, the iPhone icon,
  and link-preview cards (`frontend/public/`) from the Cs mark in `assets/brand/`. Then publish.
- `./scripts/status.sh`: what's running, ports, health, disks (read-only).
- `./scripts/deploy-startup.sh`: the complete deployment/repair (uses sudo), or run a script
  in `scripts/deploy/` to update only one part of the server.

When adding a deployment stage, create `scripts/deploy/<name>.sh`, document it
in `scripts/deploy/README.md`, and add its name to the loop in
`deploy-startup.sh` only if every full deployment should run it.
