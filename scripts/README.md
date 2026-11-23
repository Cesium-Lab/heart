# Scripts

Run `./scripts/deploy-startup.sh` for the complete deployment, or run a script
in `scripts/deploy/` to update only one part of the server.

When adding a deployment stage, create `scripts/deploy/<name>.sh`, document it
in `scripts/deploy/README.md`, and add its name to the loop in
`deploy-startup.sh` only if every full deployment should run it.
