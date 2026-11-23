# Apache configuration

- Add a domain or virtual host in `sites-available/<name>.conf`.
- Add an API route shared by the main site in `includes/api-proxies.conf`.
- Update `scripts/deploy/apache.sh` so new files and sites are installed.

Keep application servers bound to localhost and let Apache expose them.
Always run `sudo apache2ctl configtest` before reloading Apache.
