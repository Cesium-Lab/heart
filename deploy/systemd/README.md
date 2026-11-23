# systemd services

To add a service, copy a nearby `.service` file, then edit its description,
working directory, command, user, dependencies, and restart policy.

Also add the unit name to `scripts/deploy/backends.sh` for installation and to
`scripts/deploy/verify.sh` for startup and health validation. Check it with:

```bash
systemd-analyze verify deploy/systemd/<name>.service
```
