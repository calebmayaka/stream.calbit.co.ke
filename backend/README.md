# MediaHub API (Django)

JSON API behind the SvelteKit UI. Talks to Jellyfin on `10.30.0.12:8096` server-side;
metadata, artwork and subtitles use `/api/...`; video streams directly from Jellyfin.

| Route | What |
|-------|------|
| `GET /api/health` | mode + whether Jellyfin answers |
| `GET /api/home` | `{hero, rows}` for the home page (mock or live) |
| `GET /api/img/<jellyfin-id>/<Primary\|Backdrop\|Thumb>?w=400` | poster/backdrop, proxied + disk-cached (live mode only) |
| `GET /api/title/<id>` | detail page: movie, series (seasons + episodes), episode or collection; trailers, similar, cast |
| `GET /api/person/<id>` | actor bio + their titles in the library |
| `GET /api/browse?type=movies\|series\|collections\|mylist&sort=added\|title\|year\|rating\|random&genre=&start=&limit=` | paged library grid |
| `GET /api/genres?type=movies\|series` | genre chips |
| `GET /api/search?q=` | `{results, people}` |
| `POST /api/played/<id>` `{played}` / `POST /api/favorite/<id>` `{favorite}` | watched toggle / My List (Jellyfin favourites) |
| `GET /api/subs/<item>/<source>/<index>` | subtitle as cleaned WebVTT (ASS styling, karaoke, drawings stripped) |
| `POST /api/play/<id>` `{startSeconds, audioIndex?}` | stream URL (HLS or MP4) + audio/subtitle tracks, next episode, intro/credits segments |
| `POST /api/progress/<id>` `{positionSeconds, durationSeconds}` | save watch position to `JELLYFIN_USER_ID` |
| `POST /api/stop` `{playSessionId}` | stop the Jellyfin transcode |

POSTs require a JSON object and a valid CSRF token. If an Origin header is sent,
its host must be allowed. Invalid field types, non-finite numbers and out-of-range
playback positions return 400. Account strings have explicit length limits;
passwords are never silently truncated.

## Playback

The browser streams **directly from Jellyfin**. The stream URL carries a
session token for a dedicated **non-admin** Jellyfin user — never the admin API key:

1. In Jellyfin, create a user (e.g. `mediahub-stream`): not an administrator, media
   playback + video transcoding allowed, library access limited to what MediaHub shows,
   no deletion, no remote control of other users.
2. Put `JELLYFIN_STREAM_USER` / `JELLYFIN_STREAM_PASSWORD` in `.env` and restart.
   Django refuses to use the account if it is an admin.
3. Tokens and playback-session mappings are stored in the Django database. New
   playback rotates tokens after `JELLYFIN_STREAM_TOKEN_HOURS` (default 6); each
   token is due for revocation after twice that age. Issuances use distinct device IDs.
4. `serve.py` starts an independent cleanup thread at startup, then every
   `JELLYFIN_TOKEN_CLEANUP_SECONDS` (default 60). Failed revocations stay queued for
   retry. Service/database/Jellyfin downtime delays revocation; this is not a
   cryptographically enforced upstream expiry.
5. Existing cached stream tokens are imported and queued for revocation on first
   cleanup. Old credentials already evicted from the cache require revocation in
   Jellyfin's session/device management. Active legacy streams must restart.

Watch progress is written by Django (admin key, server-side) to `JELLYFIN_USER_ID`, so
Continue Watching stays on the library user rather than the stream account.

LAN viewers get `JELLYFIN_URL`; requests that arrive via Cloudflare (`CF-Connecting-IP`)
or over https get `JELLYFIN_PUBLIC_URL`.

Text subtitles and audio selection are implemented. Accounts share one Jellyfin
library profile; viewers in one token generation share a stream device. Individual
profiles and a full concurrent live-playback test remain outside this change.

## Logins

Every page and `/api/` route (except `/api/auth/*` and a bare `/api/health`) needs a
signed-in user: Django session cookie + CSRF token, with 30-day sessions. Up to five
attempts per username/IP are reserved within a 15-minute window using an atomic
conditional database update. Further attempts receive 429 until that window expires;
a successful login clears the counter. Poster-cache eviction cannot reset counters.

Manage accounts from this folder (passwords are typed at a hidden prompt):

```powershell
.venv\Scripts\python manage.py adduser caleb --name "Caleb"
.venv\Scripts\python manage.py changepassword caleb
.venv\Scripts\python manage.py removeuser someone      # also signs them out everywhere
```

## Local dev

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
# Set DJANGO_DEBUG=true, MEDIAHUB_PORT=8020 and MEDIAHUB_SECURE_COOKIES=false for HTTP dev.
# Leave POSTGRES_DB empty for SQLite, or configure your own PostgreSQL database.
New-Item -ItemType Directory -Force var | Out-Null
.venv\Scripts\python manage.py migrate --noinput
.venv\Scripts\python manage.py adduser caleb --name "Caleb"
.venv\Scripts\python manage.py runserver 127.0.0.1:8020
```

The UI's Vite dev/preview server proxies `/api` to `127.0.0.1:8020`.

`MEDIAHUB_DATA_MODE=mock` serves a canned home page and never calls Jellyfin.
Browse, detail and playback endpoints need live mode. Set it to `live`
with `JELLYFIN_API_KEY` (Dashboard → API Keys) and `JELLYFIN_USER_ID` to read the real library.

## Production on 10.30.0.11

**Deployment recorded in this project:** NSSM service `mediahub-api` (Waitress 127.0.0.1:8013, log in
`var\service.log`), IIS site `mediahub` (`C:\inetpub\mediahub`, `*:80:stream.calbit.co.ke`),
cloudflared ingress `stream.calbit.co.ke -> http://localhost:80`. Video streams from the
existing public Jellyfin hostname `https://media.calebmayaka.com` (`JELLYFIN_PUBLIC_URL`).

- Redeploy the UI: `powershell -ExecutionPolicy Bypass -File ..\mediahub\scripts\deploy.ps1`
- Restart the API after code or `.env` changes: `nssm restart mediahub-api`
- Apply pending migrations before starting updated API code (see below).
- Restore the previous UI: `powershell -ExecutionPolicy Bypass -File ..\mediahub\scripts\deploy.ps1 -Rollback`
- UI releases retain old assets and save snapshots outside IIS in
  `C:\inetpub\mediahub.releases`; no mirror deletion is used.

Original setup steps, for reference:

Same pattern as the other Django apps: NSSM → Waitress on loopback → IIS site → cloudflared.

1. **Postgres:** create a `mediahub` role + DB (as the postgres superuser), then fill the
   `POSTGRES_*` vars in `.env`. Run `manage.py migrate --noinput`: auth, sessions,
   lockouts and stream credentials all require database tables.
2. **.env:** `DJANGO_DEBUG=false`, a real `DJANGO_SECRET_KEY`, `MEDIAHUB_PORT=8013`
   (next free loopback port after 8012 as of 2026-10-22 — re-check with
   `netstat -ano | findstr LISTENING`).
3. **Service** (admin PowerShell; compare against `nssm dump jobs` first):

   ```powershell
   $app = "C:\path\to\media2\backend"
   nssm install mediahub-api "$app\.venv\Scripts\python.exe" "$app\serve.py"
   nssm set mediahub-api AppDirectory $app
   nssm set mediahub-api AppStdout "$app\var\service.log"
   nssm set mediahub-api AppStderr "$app\var\service.log"
   nssm start mediahub-api
   ```

4. **IIS:** the UI build folder is the site root; its `web.config` needs the `/api` proxy
   rule cloned from the `jobs` site, placed **before** the SPA fallback rule.

## Required upgrade and checks

Back up the database. Stop the API before applying the catalog migration, then
start it only after migration succeeds:

```powershell
nssm stop mediahub-api
.venv\Scripts\python manage.py migrate --noinput
nssm start mediahub-api
```

Production `serve.py` starts credential cleanup automatically. For a live development
server using Django `runserver`, run cleanup in a second terminal (or use `serve.py`
with `MEDIAHUB_PORT=8020` instead):

```powershell
.venv\Scripts\python manage.py revoke_stream_tokens --watch
# One maintenance pass:
.venv\Scripts\python manage.py revoke_stream_tokens
```

Run isolated tests and migration consistency checks:

```powershell
.venv\Scripts\python manage.py test catalog --settings=mediahub.test_settings --noinput
.venv\Scripts\python manage.py makemigrations --check --dry-run --settings=mediahub.test_settings
```

Tests use an in-memory database/cache and block real network calls. They cover
login, CSRF, concurrent lockout reservations, malformed requests, progress thresholds,
idle credential expiry, legacy-token import, revocation retry, and stopping an older
playback session after token rotation. Never use test settings for a running app.

Monitor `var/service.log` for cleanup failures and verify login and actual playback
after release. Database backups contain session and playback credentials; protect
them like `.env`. Frontend rollback does not undo database or Python changes.
