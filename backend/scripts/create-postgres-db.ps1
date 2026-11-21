<#
  Creates MediaHub's own PostgreSQL role + database (like the other apps on this
  box) and writes the POSTGRES_* settings into backend\.env.

  Run it yourself from the backend folder; it asks for the postgres superuser
  password (hidden). The mediahub role gets a random password nobody types.
      powershell -ExecutionPolicy Bypass -File scripts\create-postgres-db.ps1

  Safe to re-run: existing role/database are kept, the role's password is reset.
#>
param(
    [string]$DbName = "mediahub",
    [string]$DbUser = "mediahub",
    [string]$PgHost = "127.0.0.1",
    [int]$PgPort = 5432
)

$ErrorActionPreference = "Stop"
$psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
if (-not $psql) { throw "psql.exe not found under C:\Program Files\PostgreSQL" }
$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (-not (Test-Path $envFile)) { throw "No .env at $envFile" }

$secure = Read-Host "postgres superuser password (hidden)" -AsSecureString
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))

# 32 random alphanumerics: no quoting issues in SQL or .env.
$chars = [char[]]"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$appPassword = -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })

function Invoke-Psql([string]$Db, [string]$Sql) {
    $out = $Sql | & $psql -h $PgHost -p $PgPort -U postgres -d $Db -v ON_ERROR_STOP=1 -q -t -A 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $out" }
    $out
}

try {
    Invoke-Psql "postgres" @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DbUser') THEN
    CREATE ROLE "$DbUser" LOGIN PASSWORD '$appPassword';
  ELSE
    ALTER ROLE "$DbUser" WITH LOGIN PASSWORD '$appPassword';
  END IF;
END
`$`$;
"@ | Out-Null

    $exists = Invoke-Psql "postgres" "SELECT 1 FROM pg_database WHERE datname = '$DbName';"
    if (-not "$exists".Trim()) {
        Invoke-Psql "postgres" "CREATE DATABASE `"$DbName`" OWNER `"$DbUser`" ENCODING 'UTF8';" | Out-Null
        Write-Host "Created database $DbName"
    } else {
        Write-Host "Database $DbName already exists; kept it."
    }
    Invoke-Psql $DbName "REVOKE ALL ON DATABASE `"$DbName`" FROM PUBLIC; GRANT ALL ON SCHEMA public TO `"$DbUser`";" | Out-Null
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

$values = [ordered]@{
    POSTGRES_DB       = $DbName
    POSTGRES_USER     = $DbUser
    POSTGRES_PASSWORD = $appPassword
    POSTGRES_HOST     = $PgHost
    POSTGRES_PORT     = "$PgPort"
}
$lines = [System.Collections.Generic.List[string]](Get-Content $envFile)
foreach ($key in $values.Keys) {
    $i = -1
    for ($n = 0; $n -lt $lines.Count; $n++) { if ($lines[$n] -match "^\s*$key\s*=") { $i = $n; break } }
    if ($i -ge 0) { $lines[$i] = "$key=$($values[$key])" } else { $lines.Add("$key=$($values[$key])") }
}
[IO.File]::WriteAllLines($envFile, $lines)

Write-Host "Done: role '$DbUser' + database '$DbName' ready; .env updated. Restart mediahub-api to use it."
