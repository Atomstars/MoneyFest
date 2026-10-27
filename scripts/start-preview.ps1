param([int]$Port=4173)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$local=Join-Path $projectRoot '.local'
$vite=Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
if (!(Test-Path $vite)) { throw 'Install frontend dependencies first.' }
if (!(Test-Path (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Run npm run build in frontend first.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already in use." }
$node=(Get-Command node).Source
$process=Start-Process -FilePath $node -ArgumentList @("`"$vite`"",'preview','--host','127.0.0.1','--port',"$Port",'--strictPort') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $local 'preview.log') -RedirectStandardError (Join-Path $local 'preview.err.log')
@{pid=$process.Id;port=$Port} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $local 'preview.json')
for ($attempt=0;$attempt -lt 20;$attempt++) {
    try {
        $web=Invoke-WebRequest "http://127.0.0.1:$Port/" -TimeoutSec 2
        $health=Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2
        if ($web.StatusCode -eq 200 -and $health.status -eq 'ok') {
            Write-Output "Built preview ready at http://127.0.0.1:$Port"
            return
        }
    } catch { Start-Sleep -Milliseconds 500 }
}
throw 'Preview did not become ready. Check .local/preview logs.'
