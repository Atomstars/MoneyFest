$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$localDir=Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Force $localDir | Out-Null
$jarPath=Join-Path $localDir 'postgres-binaries.jar'
$download='https://repo.maven.apache.org/maven2/io/zonky/test/postgres/embedded-postgres-binaries-windows-amd64/18.6.0/embedded-postgres-binaries-windows-amd64-18.6.0.jar'
Invoke-WebRequest $download -OutFile $jarPath
$expected=(Invoke-RestMethod ($download+'.sha1')).Trim().ToLowerInvariant()
$actual=(Get-FileHash -LiteralPath $jarPath -Algorithm SHA1).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'PostgreSQL archive checksum mismatch.' }
Push-Location $projectRoot
try {
    @'
from pathlib import Path
import zipfile, tarfile
archive = Path('.local/postgres-runtime.txz')
with zipfile.ZipFile('.local/postgres-binaries.jar') as package:
    archive.write_bytes(package.read('postgres-windows-x86_64.txz'))
with tarfile.open(archive) as package:
    package.extractall('.local/postgres-runtime', filter='data')
'@ | python -
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL archive extraction failed.' }
} finally { Pop-Location }
Write-Output 'Project-local PostgreSQL runtime is ready. No system service was installed.'
