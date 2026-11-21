# VPS front door

**Live since 2026-11-22.** Contabo VPS 161.97.79.224 (Tailscale `mayakaombogo`,
100.87.36.46); `stream` and `jellyfin` A records point there (DNS only); Let's Encrypt
certs via the Docker Caddy; `JELLYFIN_PUBLIC_URL=https://jellyfin.calbit.co.ke` on .11.

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

## Our VPS: Caddy runs in Docker

The VPS already runs Caddy as the `caddy` container (Compose project in `/srv/proxy`,
network `web`), importing one file per site from `/srv/proxy/sites/`. Use:

```bash
curl -fsSLO https://raw.githubusercontent.com/calebmayaka/stream.calbit.co.ke/main/deploy/vps/install-docker-caddy.sh
sudo bash install-docker-caddy.sh '<MEDIAHUB_PROXY_KEY>'
```

It checks the container can reach the app and Jellyfin over Tailscale, writes
`stream.calbit.co.ke.caddy` and `jellyfin.calbit.co.ke.caddy` into `/srv/proxy/sites/`,
validates, and does a graceful `caddy reload` (other sites unaffected).
`setup.sh` below is for a VPS where Caddy is a system service.

**Docker routing:** containers reach Tailscale `100.x` addresses through the host. The
script tests this first and writes nothing if it fails; in that case check with
`sudo docker exec caddy wget -qO- http://100.124.178.16:8096/System/Info/Public`
before changing any host networking.

## Steps (system Caddy)

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

## TCP tuning (BBR) — applied 2026-11-22

The links home ↔ VPS (Europe, ~170-275 ms) are long, so the VPS uses BBR instead of
cubic. Through-the-VPS tests before → after: HEVC (repackaged) picture after a seek
17.5 s → 7.3 s and 1.8x → 3.5x real time; H.264 transcode 12.5 s → 7.5 s.

- Host: `tcp_bbr` loaded at boot (`/etc/modules-load.d/bbr.conf`), and
  `/etc/sysctl.d/99-bbr.conf` sets `net.core.default_qdisc=fq` and
  `net.ipv4.tcp_congestion_control=bbr`.
- The Caddy container has its own network namespace, so `/srv/proxy/compose.yml`
  sets it too (under the `caddy` service):
  ```yaml
      sysctls:
        net.ipv4.tcp_congestion_control: bbr
  ```
  Check: `sudo docker exec caddy cat /proc/sys/net/ipv4/tcp_congestion_control` → `bbr`.
- Undo: delete both, `sudo sysctl -w net.ipv4.tcp_congestion_control=cubic`,
  `cd /srv/proxy && sudo docker compose up -d caddy`.

## Rollback

Point `stream` back at the tunnel (CNAME `a75c8e81-bbec-4e6d-90b8-8916e8c33a7c.cfargotunnel.com`,
proxied) and set `JELLYFIN_PUBLIC_URL=https://media.calebmayaka.com`. The tunnel rules on
.11 are left in place for exactly this.

## Notes

- Caddy on the VPS also serves another service. MediaHub lives in
  `/etc/caddy/sites/mediahub.caddy`; the main `/etc/caddy/Caddyfile` only gets one
  `import sites/*.caddy` line (setup.sh keeps a copy as `Caddyfile.before-mediahub`).
  The first version of setup.sh overwrote the main Caddyfile — fixed.

- `MEDIAHUB_PROXY_KEY` (in `backend/.env` and `/etc/caddy/mediahub.env`) lets Django trust
  the visitor IP Caddy forwards, so login lockouts are per visitor. Without it, every
  visitor would share the proxy's address.
- Video goes home → VPS → viewer, so the home upload speed is still the ceiling per stream.
- Logs: `/var/log/caddy/{stream,jellyfin}.log`; `journalctl -u caddy`.
