#!/usr/bin/env bash

# Stop immediately if an installation or validation command fails.
set -Eeuo pipefail
# Load shared repository paths and deployment helpers.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# Confirm required host tools exist before modifying Apache.
require_command sudo
require_command apache2ctl
require_command systemctl

# Install the reusable API routes separately from the virtual-host definitions.
log "Installing Apache proxy include"
sudo install -d -m 0755 /etc/apache2/cesium
sudo install -m 0644 "${APACHE_DEPLOY_DIR}/includes/api-proxies.conf" /etc/apache2/cesium/api-proxies.conf

# Install the main site and the separately addressable DataViz site.
log "Installing Apache sites"
sudo install -m 0644 "${APACHE_DEPLOY_DIR}/sites-available/cesiumlab.conf" /etc/apache2/sites-available/cesiumlab.conf
sudo install -m 0644 "${APACHE_DEPLOY_DIR}/sites-available/dataviz.conf" /etc/apache2/sites-available/dataviz.conf
sudo a2enmod proxy proxy_http proxy_wstunnel
sudo a2ensite cesiumlab.conf dataviz.conf
sudo a2dissite 000-default.conf >/dev/null 2>&1 || true

# Refuse to reload invalid configuration, then start and reload Apache.
log "Validating and reloading Apache"
sudo apache2ctl configtest
sudo systemctl enable --now apache2.service
sudo systemctl reload apache2.service
