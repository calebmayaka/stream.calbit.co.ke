# MediaHub handoff

Updated 2026-10-25. Earlier notes describing an unbuilt backend are obsolete.

## Application

MediaHub is a Svelte 5 / SvelteKit static SPA with Tailwind 4 and a Django 5.2 API.
Jellyfin provides the media library and transcoding. Implemented features include
session login, home recommendations, browsing/filtering, search, title and cast
pages, collections, favorites, watch progress, HLS/direct playback, text subtitles,
audio selection, intro skipping, and episode autoplay. Photos and Retro are not
complete. All accounts share JELLYFIN_USER_ID and its viewing history.

## Deployment topology

The deployment recorded in this project uses:

- Web server: 10.30.0.11, Windows Server, IIS, NSSM, Waitress, PostgreSQL.
- IIS site: mediahub; C:\inetpub\mediahub; stream.calbit.co.ke on port 80.
- Cloudflare Tunnel: stream.calbit.co.ke forwards to http://localhost:80.
- NSSM service: mediahub-api, running backend/serve.py with the backend venv.
- Waitress: 127.0.0.1:8013; IIS rewrites /api/* to this address.
- Jellyfin: Django connects to http://10.30.0.12:8096; remote browsers use
  https://media.calebmayaka.com from JELLYFIN_PUBLIC_URL.

IIS serves the frontend directly; no Node service is needed. Videos travel from
Jellyfin to the browser. Artwork and subtitles are proxied/cached by Django.
Keep the separate media / media-worker application unchanged.

## Security and playback lifecycle

Django sessions and CSRF protect the API. Login-attempt reservations live in the
Django database, using a conditional SQL update before password verification.
Artwork eviction cannot reset a lockout. POST bodies must be JSON objects with
valid field types and bounded, finite playback times.

Stream credentials belong to the configured non-admin Jellyfin account. They are
stored in catalog_streamtoken, with playback-session mappings and issuance,
rotation, and revocation timestamps. New playback rotates credentials after six
hours by default. Each credential is due for revocation after twelve hours.
A background cleanup thread in serve.py runs immediately at startup and then
roughly every 60 seconds, independently of playback requests. Failed revocations
stay in the database and are retried. Actual revocation is delayed while the
service, database, or Jellyfin is unavailable. This is not upstream cryptographic
token expiry. Treat database backups as sensitive credentials.

Existing cached stream-token records are imported and revoked on first cleanup.
Credentials already lost by the old cache cannot be recovered automatically;
revoke old MediaHub sessions for the dedicated stream user in Jellyfin when
rolling out this upgrade. Active legacy streams must restart after revocation.

## Verification (from the project root)

```powershell
Push-Location backend
.\.venv\Scripts\python.exe manage.py test catalog --settings=mediahub.test_settings --noinput
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=mediahub.test_settings
Pop-Location
Push-Location mediahub
npm test
npm run build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test-deploy.ps1
Pop-Location
```

Backend tests use an isolated in-memory database/cache and block network access.
The deployment test uses disposable folders and does not publish to IIS.

## Release procedure

The credential/lockout upgrade adds a required database migration. Back up the
application database before applying it. From the backend directory on the server:

```powershell
nssm stop mediahub-api
.\.venv\Scripts\python.exe manage.py migrate --noinput
# Only start the service after migrate succeeds.
nssm start mediahub-api
```

From the project root, publish the frontend:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\mediahub\scripts\deploy.ps1
```

The script builds and stages a release, snapshots the current static site outside
the web root (C:\inetpub\mediahub.releases), copies assets, and atomically replaces
index.html last. Old hashed files remain available to existing browser tabs.
It refuses unsafe paths and serializes deploys with a lock file. Copy failures
trigger an attempt to restore the previous snapshot. A first deployment has no
previous version to restore. Non-entry files such as web.config are copied in
place; this is not an atomic switch of the entire IIS site.

To restore the previous frontend:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\mediahub\scripts\deploy.ps1 -Rollback
```

Rollback affects the frontend only. It does not revert Python code, configuration,
or database migrations. Snapshots and old assets are retained until an operator
prunes them; monitor disk usage and keep the snapshot referenced by state.json.

After release, verify /api/health, login, browsing, and playback, and inspect
backend/var/service.log for migration or credential-cleanup failures. Never print
.env values or credential-bearing playback URLs in logs or reports.

See backend/README.md for API/development details and mediahub/README.md for UI work.
