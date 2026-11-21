# VPS front door

Moves public traffic off the Cloudflare tunnel onto our own Ubuntu VPS
(8 GB RAM, 100 GB SSD, 300 Mbps). The app itself stays on 10.30.0.11.

```
before:  browser → Cloudflare → tunnel (cloudflared on .11) → IIS → Django
                                                   Jellyfin via media.calebmayaka.com (tunnel)

after:   browser → VPS (Caddy, Let's Encrypt) ──Tailscale──▶ IIS on .11 → Django
                                               ──Tailscale──▶ Jellyfin (video paths only)
```

| Name | Points at | Upstream (over Tailscale) |
|------|-----------|---------------------------|
| `stream.calbit.co.ke` | VPS public IP, DNS only | `100.103.139.106:80` — IIS site `mediahub` on "dev" (.11) |
| `jellyfin.calbit.co.ke` | VPS public IP, DNS only | `100.124.178.16:8096` — Jellyfin on "svr-media" (.12), `/videos/*` only |

## Steps

1. **Jellyfin on Tailscale.** "svr-media" (10.30.0.12) has been offline in Tailscale
   since early October — start/sign in Tailscale on that machine again.
2. **VPS** (as a sudo user):
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/calebmayaka/stream.calbit.co.ke/main/deploy/vps/setup.sh
   curl -fsSLO https://raw.githubusercontent.com/calebmayaka/stream.calbit.co.ke/main/deploy/vps/Caddyfile
   sudo bash setup.sh '<MEDIAHUB_PROXY_KEY from backend/.env on .11>'
   ```
   Approve the Tailscale login URL it prints (machine name `vps-front`).
3. **Check from the VPS** before touching DNS:
   ```bash
   curl -s -H 'Host: stream.calbit.co.ke' -H 'X-Forwarded-Proto: https' http://100.103.139.106/api/health   # {"ok": true}
   curl -s http://100.124.178.16:8096/System/Info/Public                                                     # Jellyfin JSON
   ```
4. **DNS (Cloudflare → calbit.co.ke)**: set `stream` (replacing the tunnel CNAME) and add
   `jellyfin` as **A records to the VPS IP, proxy status "DNS only"** (grey cloud). Caddy
   gets certificates within a minute of the names resolving.
5. **Server .11**: `JELLYFIN_PUBLIC_URL=https://jellyfin.calbit.co.ke` in `backend/.env`,
   then `nssm restart mediahub-api`.

## Rollback

Point `stream` back at the tunnel (CNAME `a75c8e81-bbec-4e6d-90b8-8916e8c33a7c.cfargotunnel.com`,
proxied) and set `JELLYFIN_PUBLIC_URL=https://media.calebmayaka.com`. The tunnel rules on
.11 are left in place for exactly this.

## Notes

- `MEDIAHUB_PROXY_KEY` (in `backend/.env` and `/etc/caddy/mediahub.env`) lets Django trust
  the visitor IP Caddy forwards, so login lockouts are per visitor. Without it, every
  visitor would share the proxy's address.
- Video goes home → VPS → viewer, so the home upload speed is still the ceiling per stream.
- Logs: `/var/log/caddy/{stream,jellyfin}.log`; `journalctl -u caddy`.
