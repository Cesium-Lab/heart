# Deployment stages

Each script updates one part of the host and can be run independently.

- New backend service: update `backends.sh`.
- New Apache configuration: update `apache.sh`.
- New containerized monitoring component: update `monitoring.sh`.
- New health check: update `verify.sh`.
- Shared path or helper: update `common.sh`.

Keep stages safe to rerun, and add comments around any host changes.
