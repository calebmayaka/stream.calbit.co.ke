#!/usr/bin/env bash
# One-shot setup for the MediaHub front-door VPS (Ubuntu 22.04/24.04).
#
#   curl -fsSLO https://raw.githubusercontent.com/calebmayaka/stream.calbit.co.ke/main/deploy/vps/setup.sh
#   curl -fsSLO https://raw.githubusercontent.com/calebmayaka/stream.calbit.co.ke/main/deploy/vps/Caddyfile
#   sudo bash setup.sh '<MEDIAHUB_PROXY_KEY from the server .env>'
#
# Safe to re-run. Installs Caddy + Tailscale, opens only SSH/80/443, writes the
# Caddy config and its env file, then asks Tailscale to log in (prints a URL).
set -euo pipefail

PROXY_KEY="${1:-}"
APP_UPSTREAM="${APP_UPSTREAM:-100.103.139.106:80}"          # IIS on 10.30.0.11 ("dev" on Tailscale)
JELLYFIN_UPSTREAM="${JELLYFIN_UPSTREAM:-100.124.178.16:8096}" # Jellyfin ("svr-media" on Tailscale)
HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ $EUID -ne 0 ]]; then echo "Run with sudo." >&2; exit 1; fi
if [[ ${#PROXY_KEY} -lt 24 ]]; then
  echo "Usage: sudo bash setup.sh '<MEDIAHUB_PROXY_KEY>'  (copy it from backend/.env on the server)" >&2
  exit 1
fi
if [[ ! -f "$HERE/Caddyfile" ]]; then echo "Caddyfile must sit next to setup.sh." >&2; exit 1; fi

echo "==> Base packages + automatic security updates"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq curl gnupg ufw unattended-upgrades debian-keyring debian-archive-keyring apt-transport-https
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Caddy"
if ! systemctl list-unit-files caddy.service >/dev/null 2>&1 || ! systemctl cat caddy.service >/dev/null 2>&1; then
  if command -v docker >/dev/null && docker ps --format '{{.Image}} {{.Ports}}' 2>/dev/null | grep -qiE 'caddy|:443->'; then
    echo "    Caddy (or something on :443) runs in Docker here. This script only handles"
    echo "    the system Caddy service; add deploy/vps/Caddyfile to that container's config instead."
    exit 1
  fi
fi
if ! command -v caddy >/dev/null; then
  echo "    installing from the official apt repo"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -yq caddy
fi

echo "==> Tailscale (official apt repo)"
if ! command -v tailscale >/dev/null; then
  . /etc/os-release
  curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${VERSION_CODENAME}.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${VERSION_CODENAME}.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list
  apt-get update -q
  apt-get install -yq tailscale
fi

echo "==> Firewall"
# Other services share this VPS: only add rules, never switch a firewall on
# (that could cut off ports they use).
if ufw status | grep -q '^Status: active'; then
  ufw allow OpenSSH >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  echo "    ufw active: made sure 22, 80, 443 are allowed"
else
  echo "    ufw is off; left as is (80 and 443 must be reachable from the internet)"
fi

echo "==> Caddy config (MediaHub in its own file; other sites untouched)"
install -d -m 0755 /var/log/caddy
chown caddy:caddy /var/log/caddy
# Caddy on this VPS may already serve other sites from /etc/caddy/Caddyfile.
# Never replace that file: back it up once, keep MediaHub in mediahub.caddy and
# add a single import line.
install -d -m 0755 /etc/caddy/sites
install -m 0644 "$HERE/Caddyfile" /etc/caddy/sites/mediahub.caddy
if [[ -f /etc/caddy/Caddyfile ]]; then
  cp -n /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.before-mediahub" 2>/dev/null || true
  if grep -q '^# MediaHub front door' /etc/caddy/Caddyfile; then
    echo "    !! /etc/caddy/Caddyfile is the MediaHub file from an older version of this"
    echo "    !! script, which replaced it. Restore your own Caddyfile first, then re-run."
    exit 1
  fi
fi
if ! grep -qs '^import sites/\*\.caddy' /etc/caddy/Caddyfile; then
  printf '\n# MediaHub (stream.calbit.co.ke / jellyfin.calbit.co.ke)\nimport sites/*.caddy\n' >> /etc/caddy/Caddyfile
fi
umask 077
cat > /etc/caddy/mediahub.env <<EOF
APP_UPSTREAM=${APP_UPSTREAM}
JELLYFIN_UPSTREAM=${JELLYFIN_UPSTREAM}
MEDIAHUB_PROXY_KEY=${PROXY_KEY}
EOF
chown root:caddy /etc/caddy/mediahub.env
chmod 0640 /etc/caddy/mediahub.env
install -d /etc/systemd/system/caddy.service.d
cat > /etc/systemd/system/caddy.service.d/mediahub.conf <<'EOF'
[Service]
EnvironmentFile=/etc/caddy/mediahub.env
EOF
systemctl daemon-reload
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile --envfile /etc/caddy/mediahub.env >/dev/null
systemctl enable caddy >/dev/null
# Restart (not reload) so the new EnvironmentFile is picked up; other sites
# blip for a second.
systemctl restart caddy

echo "==> Tailscale login"
if tailscale status >/dev/null 2>&1; then
  echo "    already connected as $(tailscale ip -4 | head -1)"
else
  echo "    Open the URL below and approve this machine (name it 'vps-front')."
  tailscale up --hostname=vps-front
fi

echo
echo "Done. Next: point DNS for stream.calbit.co.ke and jellyfin.calbit.co.ke at this"
echo "server's public IP (DNS only / grey cloud). Caddy fetches HTTPS certificates"
echo "by itself as soon as the names resolve here."
echo "Public IP: $(curl -fsS4 https://ifconfig.me 2>/dev/null || echo '?')"
