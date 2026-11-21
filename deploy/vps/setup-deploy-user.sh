#!/usr/bin/env bash
# Create the restricted "mediahub-deploy" user that the home server uses to copy
# the built MediaHub app to this VPS (served by Caddy from /srv/apps/mediahub).
#
#   curl -fsSLO https://raw.githubusercontent.com/calebmayaka/stream.calbit.co.ke/main/deploy/vps/setup-deploy-user.sh
#   sudo bash setup-deploy-user.sh 'ssh-ed25519 AAAA... mediahub-deploy@dev'
#
# The user has no password and no sudo. Its key only works over Tailscale
# (100.64.0.0/10), with no port/agent/X11 forwarding, and it can only write to
# /srv/apps/mediahub. Safe to re-run (replaces the key).
set -euo pipefail

KEY="${1:-}"
USER_NAME="mediahub-deploy"
APP_DIR="/srv/apps/mediahub"

if [[ $EUID -ne 0 ]]; then echo "Run with sudo." >&2; exit 1; fi
if [[ ! "$KEY" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]]; then
  echo "Usage: sudo bash setup-deploy-user.sh 'ssh-ed25519 AAAA... mediahub-deploy@dev'" >&2; exit 1
fi

echo "==> User $USER_NAME (no password, no sudo)"
if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$USER_NAME"
fi
passwd -l "$USER_NAME" >/dev/null           # no password logins, ever
gpasswd -d "$USER_NAME" sudo >/dev/null 2>&1 || true

echo "==> App folder $APP_DIR (owned by $USER_NAME, readable by Caddy)"
install -d -m 0755 /srv/apps
install -d -m 0755 -o "$USER_NAME" -g "$USER_NAME" "$APP_DIR" "$APP_DIR/releases"

echo "==> SSH key: Tailscale only, no forwarding"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
install -d -m 0700 -o "$USER_NAME" -g "$USER_NAME" "$HOME_DIR/.ssh"
printf 'from="100.64.0.0/10",restrict %s\n' "$KEY" > "$HOME_DIR/.ssh/authorized_keys"
chown "$USER_NAME:$USER_NAME" "$HOME_DIR/.ssh/authorized_keys"
chmod 0600 "$HOME_DIR/.ssh/authorized_keys"

echo
echo "Done. Tailscale IP of this VPS: $(tailscale ip -4 2>/dev/null | head -1 || echo '?')"
echo "The home server can now deploy to $APP_DIR as $USER_NAME."
