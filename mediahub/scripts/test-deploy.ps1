# Exercise deployment using disposable folders; never writes to IIS.
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')
$testRoot = Join-Path $projectRoot ('.deployment-test-' + [guid]::NewGuid().ToString('N'))
$testProject = Join-Path $testRoot 'project'
$scripts = Join-Path $testProject 'scripts'
$build = Join-Path $testProject 'build'
$site = Join-Path $testRoot 'site'
function Assert($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
try {
    New-Item -ItemType Directory -Path $scripts, (Join-Path $build '_app\immutable') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'deploy.ps1') -Destination $scripts
    $deploy = Join-Path $scripts 'deploy.ps1'
    Set-Content -LiteralPath (Join-Path $build 'web.config') -Value '<configuration />'
    Set-Content -LiteralPath (Join-Path $build 'index.html') -Value 'release-one'
    Set-Content -LiteralPath (Join-Path $build '_app\immutable\one.js') -Value 'one'
    & $deploy -Target $site -SkipBuild
    Assert ((Get-Content -LiteralPath (Join-Path $site 'index.html') -Raw).Trim() -eq 'release-one') 'Initial deploy failed'

    Set-Content -LiteralPath (Join-Path $build 'index.html') -Value 'release-two'
    Remove-Item -LiteralPath (Join-Path $build '_app\immutable\one.js')
    Set-Content -LiteralPath (Join-Path $build '_app\immutable\two.js') -Value 'two'
    & $deploy -Target $site -SkipBuild
    Assert ((Get-Content -LiteralPath (Join-Path $site 'index.html') -Raw).Trim() -eq 'release-two') 'Second deploy failed'
    Assert (Test-Path -LiteralPath (Join-Path $site '_app\immutable\one.js')) 'Old tab asset was removed'
    & $deploy -Target $site -Rollback
    Assert ((Get-Content -LiteralPath (Join-Path $site 'index.html') -Raw).Trim() -eq 'release-one') 'Rollback failed'
    Assert (Test-Path -LiteralPath (Join-Path $site '_app\immutable\two.js')) 'Rollback removed newer tab assets'

    Remove-Item -LiteralPath (Join-Path $build 'index.html')
    $refused = $false
    try { & $deploy -Target $site -SkipBuild } catch { $refused = $true }
    Assert $refused 'Incomplete build was accepted'
    Assert ((Get-Content -LiteralPath (Join-Path $site 'index.html') -Raw).Trim() -eq 'release-one') 'Failed deploy altered the entry page'
    $refused = $false
    try { & $deploy -Target $testProject -SkipBuild } catch { $refused = $true }
    Assert $refused 'Source directory was accepted as a deployment target'
    Write-Host 'PASS: initial deploy, update, retained assets, rollback, failed build, unsafe target'
} finally {
    if (Test-Path -LiteralPath $testRoot) {
        $resolved = (Resolve-Path -LiteralPath $testRoot).Path
        if (-not $resolved.StartsWith($projectRoot + '\.deployment-test-', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing cleanup outside the test workspace: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
