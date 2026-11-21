<#
  Publish the built SPA to the VPS, where Caddy serves it straight from
  /srv/apps/mediahub/current (only /api goes home over Tailscale).

      powershell -ExecutionPolicy Bypass -File scripts\deploy-vps.ps1            (uses build\)
      powershell -ExecutionPolicy Bypass -File scripts\deploy-vps.ps1 -Rollback  (previous release)

  Run scripts\deploy.ps1 first (it builds and updates IIS, the fallback).
  Connects as the restricted "mediahub-deploy" user (deploy/vps/setup-deploy-user.sh)
  with ~\.ssh\mediahub_deploy, over Tailscale only.
#>
[CmdletBinding()]
param(
    [string]$VpsHost = "100.87.36.46",           # VPS on Tailscale ("mayakaombogo")
    [string]$User = "mediahub-deploy",
    [string]$Key = (Join-Path $env:USERPROFILE ".ssh\mediahub_deploy"),
    [switch]$Rollback
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$build = Join-Path $root "build"
$sshArgs = @("-i", $Key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
             "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15")
$target = "$User@$VpsHost"

function Invoke-Remote([string]$Script) {
    # The script travels on stdin so no quoting survives PowerShell's native-arg rules.
    $Script -replace "`r", "" | & ssh.exe @sshArgs $target "bash -s"
    if ($LASTEXITCODE -ne 0) { throw "Remote step failed ($LASTEXITCODE)" }
}

if ($Rollback) {
    Invoke-Remote @'
set -euo pipefail
cd /srv/apps/mediahub
cur=$(readlink current)
prev=$(ls -1dt releases/*/ | sed 's#/$##' | grep -vx "$cur" | head -1)
[ -n "$prev" ] || { echo "No previous release." >&2; exit 1; }
ln -sfn "$prev" current.tmp && mv -Tf current.tmp current
echo "Rolled back: $cur -> $prev"
'@
    return
}

if (-not (Test-Path (Join-Path $build "index.html"))) { throw "No build\index.html - run scripts\deploy.ps1 (or npm run build) first." }
$id = (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 6)
$archive = Join-Path ([IO.Path]::GetTempPath()) "mediahub-$id.tgz"
try {
    & tar.exe -czf $archive -C $build .
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }
    & scp.exe @sshArgs -q $archive "${target}:/srv/apps/mediahub/upload-$id.tgz"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed ($LASTEXITCODE)" }
} finally {
    Remove-Item $archive -ErrorAction SilentlyContinue
}

Invoke-Remote @"
set -euo pipefail
cd /srv/apps/mediahub
id='$id'
mkdir "releases/`$id"
tar -xzf "upload-`$id.tgz" -C "releases/`$id" && rm -f "upload-`$id.tgz"
rm -f "releases/`$id/web.config"                  # IIS-only, never serve it
test -f "releases/`$id/index.html"
# Keep older content-hashed chunks so tabs opened before this deploy still load.
if [ -d current/_app/immutable ]; then cp -rn current/_app/immutable/. "releases/`$id/_app/immutable/"; fi
chmod -R a+rX "releases/`$id"
ln -sfn "releases/`$id" current.tmp && mv -Tf current.tmp current
# Keep the newest 5 releases (never the live one).
live=`$(readlink current)
ls -1dt releases/*/ | sed 's#/$##' | tail -n +6 | while read -r d; do [ "`$d" = "`$live" ] || rm -rf "`$d"; done
echo "Live on VPS: `$live"
"@
