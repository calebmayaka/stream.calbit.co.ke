#!/usr/bin/env bash
# Add MediaHub to the Docker Caddy on the VPS (/srv/proxy, container "caddy").
#
# That Caddy imports sites/*.caddy, one file per site, so this only writes
#   /srv/proxy/sites/stream.calbit.co.ke.caddy
#   /srv/proxy/sites/jellyfin.calbit.co.ke.caddy
# and does a graceful `caddy reload` (other sites keep running, no downtime).
#
#   curl -fsSLO https://raw.githubusercontent.com/calebmayaka/stream.calbit.co.ke/main/deploy/vps/install-docker-caddy.sh
#   sudo bash install-docker-caddy.sh '<MEDIAHUB_PROXY_KEY from backend/.env on .11>'
set -euo pipefail

KEY="${1:-}"
APP="${APP_UPSTREAM:-100.103.139.106:80}"          # IIS on 10.30.0.11 ("dev" on Tailscale)
JF="${JELLYFIN_UPSTREAM:-100.124.178.16:8096}"      # Jellyfin ("svr-media" on Tailscale)
SITES="${SITES_DIR:-/srv/proxy/sites}"
C="${CADDY_CONTAINER:-caddy}"

if [[ $EUID -ne 0 ]]; then echo "Run with sudo." >&2; exit 1; fi
if [[ ! "$KEY" =~ ^[A-Za-z0-9_-]{24,}$ ]]; then
  echo "Usage: sudo bash install-docker-caddy.sh '<MEDIAHUB_PROXY_KEY>'" >&2; exit 1
fi
if [[ ! -d "$SITES" ]]; then echo "No $SITES directory." >&2; exit 1; fi
docker inspect "$C" >/dev/null 2>&1 || { echo "No container named '$C'." >&2; exit 1; }

echo "==> Can the Caddy container reach home over Tailscale?"
ok=1
if docker exec "$C" wget -q -T 6 -O- --header 'Host: stream.calbit.co.ke' --header 'X-Forwarded-Proto: https' \
     "http://$APP/api/health" 2>/dev/null | grep -q '"ok"'; then
  echo "    MediaHub app ($APP): ok"
else
  echo "    MediaHub app ($APP): NOT reachable from the container"; ok=0
fi
if docker exec "$C" wget -q -T 6 -O- "http://$JF/System/Info/Public" 2>/dev/null | grep -q 'Jellyfin'; then
  echo "    Jellyfin ($JF): ok"
else
  echo "    Jellyfin ($JF): NOT reachable from the container"; ok=0
fi
if [[ $ok -ne 1 ]]; then
  echo "Nothing written. The host reaches Tailscale but the container doesn't; see" >&2
  echo "deploy/vps/README.md (Docker routing) before retrying." >&2
  exit 1
fi

echo "==> Writing site files"
for f in stream.calbit.co.ke.caddy jellyfin.calbit.co.ke.caddy; do
  [[ -f "$SITES/$f" ]] && cp "$SITES/$f" "$SITES/$f.bak.$(date +%Y%m%d%H%M%S)"
done

umask 077   # the stream file holds the proxy key
PROXY_BLOCK="reverse_proxy $APP {
		# IIS routes by host name; Django's CSRF check expects the public one.
		header_up Host stream.calbit.co.ke
		header_up X-Forwarded-Proto https
		# Visitor address for the login lockout, believed only with the key.
		header_up X-MediaHub-Client-IP {remote_host}
		header_up X-MediaHub-Proxy-Key $KEY
		header_up -CF-Connecting-IP
	}"

if [[ -f /srv/apps/mediahub/current/index.html ]]; then
  echo "    app files found in /srv/apps/mediahub/current: serving them from the VPS"
  cat > "$SITES/stream.calbit.co.ke.caddy" <<EOF
# MediaHub. App files are served here on the VPS (deployed by
# mediahub/scripts/deploy-vps.ps1); only /api goes home to Django over
# Tailscale. Managed by deploy/vps/install-docker-caddy.sh.
stream.calbit.co.ke {
	encode zstd gzip
	header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"

	handle /api/* {
		$PROXY_BLOCK
	}

	handle {
		root * /srv/apps/mediahub/current
		# Content-hashed build output never changes; everything else revalidates
		# so a new deploy shows up immediately.
		@immutable path /_app/immutable/*
		header @immutable Cache-Control "public, max-age=31536000, immutable"
		header ?Cache-Control "no-cache"
		# SPA: unknown paths (/title/..., /movies) get the app shell.
		try_files {path} /index.html
		file_server
	}
}
EOF
else
  echo "    no app files on the VPS yet: proxying everything home (run deploy-vps.ps1, then re-run this)"
  cat > "$SITES/stream.calbit.co.ke.caddy" <<EOF
# MediaHub app -> IIS on 10.30.0.11 over Tailscale. Managed by
# deploy/vps/install-docker-caddy.sh (github.com/calebmayaka/stream.calbit.co.ke).
stream.calbit.co.ke {
	encode zstd gzip
	$PROXY_BLOCK
}
EOF
fi

umask 022
cat > "$SITES/jellyfin.calbit.co.ke.caddy" <<EOF
# MediaHub video -> Jellyfin over Tailscale. Only /videos/* (HLS + direct
# files); Jellyfin's web UI, login and admin API stay off the internet.
jellyfin.calbit.co.ke {
	@video path /videos/* /Videos/*
	handle @video {
		reverse_proxy $JF {
			flush_interval -1
		}
	}
	handle {
		respond "Not here." 404
	}
}
EOF

echo "==> Validate + graceful reload"
if ! docker exec "$C" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null; then
  echo "Config invalid; removing the new files so nothing changes." >&2
  rm -f "$SITES/stream.calbit.co.ke.caddy" "$SITES/jellyfin.calbit.co.ke.caddy"
  exit 1
fi
docker exec "$C" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
echo
echo "Done. Caddy is fetching certificates for stream.calbit.co.ke and"
echo "jellyfin.calbit.co.ke now; follow with:  sudo docker logs -f --since 2m $C"
