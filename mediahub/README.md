# MediaHub frontend

Svelte 5 / SvelteKit + Tailwind 4 static SPA for the Django/Jellyfin application.
The UI includes login, movies/series, collections, My List, search, title and cast
pages, and an hls.js/native video player with audio/subtitle selection and autoplay.
All content requests go through src/lib/data/api.js. Photos and Retro remain
unfinished; accounts currently share a single Jellyfin library profile.

## Development and verification

Start the backend on 127.0.0.1:8020 (see ../backend/README.md), then:

```powershell
npm ci
npm run dev
npm test
npm run build
npm run preview
```

Both Vite dev (5173) and preview (4173) proxy /api to the backend. Django must trust
the corresponding browser origin for login POSTs. Mock mode supplies only the home
page; detail/browse/playback routes need a configured live Jellyfin connection.

npm test uses Node's built-in test runner for the media-event autoplay controller.
It covers paused/buffering/seeking playback, cancellation, cleanup, and duplicate
next-episode events. The countdown advances only while the video can actually play.

## Deployment and rollback

adapter-static writes the SPA to build/, with index.html as the route fallback.
IIS serves it from C:\inetpub\mediahub; static/web.config supplies HTTPS redirects,
the /api proxy to Waitress on port 8013, route fallback, and immutable-asset caching.
No Node process is required in production.

From this directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\deploy.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\deploy.ps1 -Rollback
```

Deployments stage a validated build and save the previous site in the sibling
C:\inetpub\mediahub.releases directory. Assets are copied before index.html is
atomically replaced. Old content-hashed assets remain for open tabs; the script
no longer mirrors/deletes site files. A failed publish attempts to restore the
snapshot. Rollback replaces frontend files only, preserving old and newer hashed
assets. The script does not roll back backend code or database migrations.

Use -Target for a different dedicated site directory outside the source project.
-SkipBuild publishes an already verified build. Snapshots/old assets are not
automatically pruned. Keep the snapshot referenced by the release state.json.

Test deploy/update/rollback without touching IIS:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test-deploy.ps1
```

## Code map

- src/routes/+layout.js: authentication gate.
- src/lib/data/api.js: API and CSRF handling; poster placeholders.
- src/lib/components/BrowsePage.svelte: shared paginated grid.
- src/lib/components/Player.svelte: playback UI, tracks, and progress.
- src/lib/playback/autoplay.js: media-event countdown and one-time transitions.
- src/app.css: visual design tokens.

See ../HANDOFF.md for the full deployment and required backend migration procedure.
