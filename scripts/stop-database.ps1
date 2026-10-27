param([string]$PostgresBin = 'C:\Program Files\PostgreSQL\18\bin')
$projectRoot = Split-Path $PSScriptRoot -Parent
if (!(Test-Path (Join-Path $PostgresBin 'pg_ctl.exe'))) { $PostgresBin = Join-Path $projectRoot '.local\postgres-runtime\bin' }
& (Join-Path $PostgresBin 'pg_ctl.exe') -D (Join-Path $projectRoot '.local\postgres') -m fast -w stop
