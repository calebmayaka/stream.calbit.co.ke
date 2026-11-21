<#
  Build and publish the static SPA, or restore the previous frontend snapshot.
  Assets are copied before index.html. Old hashed assets remain for open tabs.
  Snapshots and state live beside the site, in <Target>.releases (outside IIS).
#>
[CmdletBinding()]
param(
    [string]$Target = "C:\inetpub\mediahub",
    [switch]$Rollback,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')
$siteRoot = [IO.Path]::GetFullPath($Target).TrimEnd('\')
$releaseRoot = "$siteRoot.releases"
$buildRoot = Join-Path $projectRoot 'build'

function Test-Within([string]$Child, [string]$Parent) {
    return $Child.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or
        $Child.StartsWith($Parent.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoReparse([string]$Path) {
    $cursor = $Path
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Deployment paths cannot traverse links or junctions: $cursor"
            }
        }
        $cursor = Split-Path $cursor -Parent
    }
    if (Test-Path -LiteralPath $Path -PathType Container) {
        $link = Get-ChildItem -LiteralPath $Path -Recurse -Force |
            Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } |
            Select-Object -First 1
        if ($link) { throw "Deployment tree contains a link or junction: $($link.FullName)" }
    }
}

function Assert-Release([string]$Path) {
    Assert-NoReparse $Path
    foreach ($name in @('index.html', 'web.config')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Path $name) -PathType Leaf)) {
            throw "Incomplete release: $Path is missing $name"
        }
    }
    $null = [xml](Get-Content -LiteralPath (Join-Path $Path 'web.config') -Raw)
}

function Copy-Tree([string]$Source, [string]$Destination, [switch]$WithoutIndex) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $copyArgs = @($Source, $Destination, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    if ($WithoutIndex) { $copyArgs += @('/XF', 'index.html') }
    & robocopy.exe @copyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "File copy failed ($LASTEXITCODE): $Source -> $Destination" }
}

function Replace-File([string]$Temporary, [string]$Destination) {
    if (Test-Path -LiteralPath $Destination) {
        # Windows PowerShell 5 converts $null to an empty string for this API.
        $backup = "$Temporary.previous"
        [IO.File]::Replace($Temporary, $Destination, $backup)
        Remove-Item -LiteralPath $backup
    } else {
        [IO.File]::Move($Temporary, $Destination)
    }
}

function Publish-Release([string]$Source) {
    Assert-Release $Source
    # No /MIR: existing tabs may still request an older content-hashed chunk.
    Copy-Tree $Source $siteRoot -WithoutIndex
    $entry = Join-Path $siteRoot 'index.html'
    $temporary = Join-Path $siteRoot ('.index-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::Copy((Join-Path $Source 'index.html'), $temporary)
        Replace-File $temporary $entry
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
    }
}

if ($siteRoot -eq [IO.Path]::GetPathRoot($siteRoot).TrimEnd('\') -or
    (Test-Within $siteRoot $projectRoot) -or (Test-Within $projectRoot $siteRoot)) {
    throw 'Target must be a dedicated site directory outside the source project, not a drive root or parent directory.'
}
Assert-NoReparse $siteRoot
Assert-NoReparse $releaseRoot
if ((Test-Path -LiteralPath $siteRoot) -and (Get-ChildItem -LiteralPath $siteRoot -Force | Select-Object -First 1)) {
    Assert-Release $siteRoot
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
$lock = [IO.File]::Open((Join-Path $releaseRoot 'deploy.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$statePath = Join-Path $releaseRoot 'state.json'
$snapshot = $null
$publishing = $false
Push-Location $projectRoot
try {
    $releaseId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    if ($Rollback) {
        if (-not (Test-Path -LiteralPath $statePath)) { throw 'No previous deployment is recorded.' }
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if (-not $state.previous) { throw 'No previous deployment is available.' }
        $source = [IO.Path]::GetFullPath($state.previous)
        if (-not (Test-Within $source $releaseRoot) -or $source -eq $releaseRoot) {
            throw 'Invalid rollback snapshot path.'
        }
        Assert-Release $source
    } else {
        if (-not $SkipBuild) {
            npm run build
            if ($LASTEXITCODE -ne 0) { throw 'npm run build failed' }
        }
        Assert-Release $buildRoot
        $source = Join-Path $releaseRoot "release-$releaseId"
        Copy-Tree $buildRoot $source
        Assert-Release $source
    }

    if (Test-Path -LiteralPath (Join-Path $siteRoot 'index.html')) {
        $snapshot = Join-Path $releaseRoot "snapshot-$releaseId"
        Copy-Tree $siteRoot $snapshot
        Assert-Release $snapshot
    }
    $publishing = $true
    Publish-Release $source
    $temporaryState = Join-Path $releaseRoot "state-$releaseId.tmp"
    @{ previous = $snapshot; published = $source; deployedAt = [DateTime]::UtcNow.ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $temporaryState -Encoding UTF8
    Replace-File $temporaryState $statePath
    $publishing = $false
    Write-Host "Published $source -> $siteRoot"
    if ($snapshot) { Write-Host "Rollback snapshot: $snapshot" }
} catch {
    if ($publishing -and $snapshot) {
        try { Publish-Release $snapshot; Write-Warning 'Deployment failed; restored the previous entry page and files.' }
        catch { Write-Warning "Automatic restore failed. Snapshot retained at $snapshot. $($_.Exception.Message)" }
    }
    throw
} finally {
    Pop-Location
    $lock.Dispose()
}
