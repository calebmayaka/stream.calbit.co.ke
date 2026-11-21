<#
  Creates the limited Jellyfin account MediaHub streams with, then stores its
  password in backend\.env (JELLYFIN_STREAM_PASSWORD).

  Run it yourself from the backend folder (you type the password, nobody else sees it):
      powershell -ExecutionPolicy Bypass -File scripts\create-stream-user.ps1
  Preview without changing anything:
      powershell -ExecutionPolicy Bypass -File scripts\create-stream-user.ps1 -DryRun

  The account: not an admin, hidden from the login screen, may play + transcode,
  sees only the Movies and Shows libraries, cannot delete, download, manage
  Live TV or control other users' sessions.
#>
param(
    [string]$UserName = "mediahub-stream",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (-not (Test-Path $envFile)) { throw "No .env at $envFile" }

$cfg = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { $cfg[$Matches[1]] = $Matches[2].Trim() }
}
$base = $cfg["JELLYFIN_URL"].TrimEnd("/")
if (-not $cfg["JELLYFIN_API_KEY"]) { throw "JELLYFIN_API_KEY missing in .env" }
$headers = @{ Authorization = 'MediaBrowser Client="MediaHub", Device="MediaHub Setup", DeviceId="mediahub-setup", Version="0.1.0", Token="' + $cfg["JELLYFIN_API_KEY"] + '"' }

function Invoke-Jf([string]$Method, [string]$Path, $Body) {
    $req = @{ Method = $Method; Uri = "$base$Path"; Headers = $headers; ContentType = "application/json" }
    if ($null -ne $Body) { $req.Body = ($Body | ConvertTo-Json -Depth 6 -Compress) }
    Invoke-RestMethod @req
}

# Libraries the account may see: movies + tvshows only.
$folders = (Invoke-Jf GET "/Library/MediaFolders").Items |
    Where-Object { $_.CollectionType -in @("movies", "tvshows") }
Write-Host "Libraries to allow:" ($folders | ForEach-Object { "$($_.Name) ($($_.CollectionType))" }) -Separator "`n  "

$existing = (Invoke-Jf GET "/Users") | Where-Object { $_.Name -eq $UserName }
if ($existing) { Write-Host "User '$UserName' already exists ($($existing.Id)); its policy will be reset and its password changed." }

if ($DryRun) {
    Write-Host "`nDry run: nothing created or changed."
    return
}

$secure = Read-Host "Password for '$UserName' (hidden)" -AsSecureString
$confirm = Read-Host "Repeat password" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
$plain2 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($confirm))
if ($plain -ne $plain2) { throw "Passwords don't match." }
if ($plain.Length -lt 12) { throw "Use at least 12 characters." }
if ($plain -match '[\r\n]') { throw "Password can't contain line breaks." }

if ($existing) {
    $userId = $existing.Id
    Invoke-Jf POST "/Users/$userId/Password" @{ NewPw = $plain; ResetPassword = $false } | Out-Null
} else {
    $userId = (Invoke-Jf POST "/Users/New" @{ Name = $UserName; Password = $plain }).Id
}

# Start from the server's own policy object (it carries required provider ids), then lock it down.
$policy = (Invoke-Jf GET "/Users/$userId").Policy
$set = @{
    IsAdministrator                  = $false
    IsHidden                         = $true
    IsDisabled                       = $false
    EnableMediaPlayback              = $true
    EnableVideoPlaybackTranscoding   = $true
    EnableAudioPlaybackTranscoding   = $true
    EnablePlaybackRemuxing           = $true
    EnableRemoteAccess               = $true   # needed later for viewers via the tunnel
    EnableContentDeletion            = $false
    EnableContentDeletionFromFolders = @()
    EnableContentDownloading         = $false
    EnableSyncTranscoding            = $false
    EnableMediaConversion            = $false
    EnableLiveTvAccess               = $false
    EnableLiveTvManagement           = $false
    EnableRemoteControlOfOtherUsers  = $false
    EnableSharedDeviceControl        = $false
    EnablePublicSharing              = $false
    EnableCollectionManagement       = $false
    EnableSubtitleManagement         = $false
    EnableLyricManagement            = $false
    EnableUserPreferenceAccess       = $false
    EnableAllFolders                 = $false
    EnabledFolders                   = @($folders | ForEach-Object { $_.Id })
    EnableAllChannels                = $false
    EnabledChannels                  = @()
}
foreach ($k in $set.Keys) {
    if ($policy.PSObject.Properties.Name -contains $k) { $policy.$k = $set[$k] }
    else { $policy | Add-Member -NotePropertyName $k -NotePropertyValue $set[$k] }
}
Invoke-Jf POST "/Users/$userId/Policy" $policy | Out-Null

# Write the credentials into .env (replace the lines, or append them).
$lines = [System.Collections.Generic.List[string]](Get-Content $envFile)
foreach ($pair in @(@("JELLYFIN_STREAM_USER", $UserName), @("JELLYFIN_STREAM_PASSWORD", $plain))) {
    $i = -1
    for ($n = 0; $n -lt $lines.Count; $n++) { if ($lines[$n] -match "^\s*$($pair[0])\s*=") { $i = $n; break } }
    if ($i -ge 0) { $lines[$i] = "$($pair[0])=$($pair[1])" } else { $lines.Add("$($pair[0])=$($pair[1])") }
}
[IO.File]::WriteAllLines($envFile, $lines)   # UTF-8 without BOM, which python-dotenv expects

Write-Host "`nDone: '$UserName' ($userId) is a limited, hidden user; .env updated. Restart the MediaHub API."
