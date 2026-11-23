# Deployment configuration

- `systemd/` contains service units copied to `/etc/systemd/system/`.
- `apache/` contains sites and shared proxy configuration copied under
  `/etc/apache2/`.

After adding configuration here, update the matching installer in
`scripts/deploy/` and add a check to `scripts/deploy/verify.sh`.
