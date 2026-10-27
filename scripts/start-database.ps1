param([string]$PostgresBin = 'C:\Program Files\PostgreSQL\18\bin')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$dataDir = Join-Path $projectRoot '.local\postgres'
$logPath = Join-Path $projectRoot '.local\postgres.log'
if (!(Test-Path (Join-Path $PostgresBin 'initdb.exe'))) { $PostgresBin = Join-Path $projectRoot '.local\postgres-runtime\bin' }
if (!(Test-Path (Join-Path $PostgresBin 'initdb.exe'))) { throw 'PostgreSQL binaries not found. Supply -PostgresBin.' }
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot '.local') | Out-Null
if (!(Test-Path (Join-Path $dataDir 'PG_VERSION'))) {
    # Trust is confined to this explicitly local, loopback-only development cluster.
    & (Join-Path $PostgresBin 'initdb.exe') -D $dataDir -U moneyfest --auth=trust --encoding=UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
}
& (Join-Path $PostgresBin 'pg_ctl.exe') -D $dataDir status *> $null
if ($LASTEXITCODE -ne 0) {
    & (Join-Path $PostgresBin 'pg_ctl.exe') -D $dataDir -l $logPath -o '-h 127.0.0.1 -p 55432' -w start
    if ($LASTEXITCODE -ne 0) { throw 'Database startup failed. Inspect .local/postgres.log.' }
}
$jarPath=Join-Path $projectRoot 'backend\target\moneyfest-backend-0.1.0.jar'
if (!(Test-Path $jarPath)) { throw 'Build backend first: cd backend; ./mvnw.cmd -DskipTests package' }
& java -Xmx64m -XX:ActiveProcessorCount=2 -jar $jarPath --init-local-databases
if ($LASTEXITCODE -ne 0) { throw 'Local database bootstrap failed.' }
Write-Output 'MoneyFest database is ready on 127.0.0.1:55432.'
