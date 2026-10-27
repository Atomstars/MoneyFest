param([int]$ApiPort=8080,[int]$WebPort=5174,[switch]$TestDatabase,[switch]$SkipBuild,[switch]$Lan)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
foreach ($port in @($ApiPort,$WebPort)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is already in use. Choose a different port." }
}
if (!$SkipBuild) {
    Push-Location (Join-Path $projectRoot 'backend')
    try { & './mvnw.cmd' '-q' '-DskipTests' 'package'; if ($LASTEXITCODE -ne 0) { throw 'Backend build failed.' } }
    finally { Pop-Location }
}
& (Join-Path $PSScriptRoot 'start-database.ps1')
$jarPath=Join-Path $projectRoot 'backend\target\moneyfest-backend-0.1.0.jar'
if (!(Test-Path $jarPath)) { throw 'Backend jar is missing. Run without -SkipBuild.' }
$dbName=if ($TestDatabase) {'moneyfest_test'} else {'moneyfest'}
$runtimeJar=Join-Path $projectRoot ".local\backend-$ApiPort.jar"
Copy-Item -LiteralPath $jarPath -Destination $runtimeJar
$javaArgs=@('-Xms32m','-Xmx128m','-XX:+UseSerialGC','-XX:TieredStopAtLevel=1','-XX:ActiveProcessorCount=2','-XX:ReservedCodeCacheSize=32m','-jar',('"'+$runtimeJar+'"'),'--spring.profiles.active=local',"--server.port=$ApiPort", "--spring.datasource.url=jdbc:postgresql://127.0.0.1:55432/$dbName",'--debug=false')
# On Windows the operating-system root store includes certificates absent from some JDK bundles.
$javaArgs = @('-Djavax.net.ssl.trustStoreType=Windows-ROOT','-Djavax.net.ssl.trustStore=NONE') + $javaArgs
if ($TestDatabase) { $javaArgs += '--moneyfest.market.enabled=false' }
$javaPath=Join-Path $env:JAVA_HOME 'bin\java.exe'
if (!(Test-Path $javaPath)) { throw 'JAVA_HOME must point to your JDK.' }
$apiProcess=Start-Process -FilePath $javaPath -ArgumentList $javaArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot ".local\api-$ApiPort.log") -RedirectStandardError (Join-Path $projectRoot ".local\api-$ApiPort.err.log")
$previousApi=$env:MONEYFEST_API_URL
try {
    $env:MONEYFEST_API_URL="http://127.0.0.1:$ApiPort"
    $vitePath=Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
    $webHost=if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
    $webProcess=Start-Process -FilePath (Get-Command node).Source -ArgumentList @(('"'+$vitePath+'"'),'--host',$webHost,'--port',"$WebPort",'--strictPort') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot ".local\web-$WebPort.log") -RedirectStandardError (Join-Path $projectRoot ".local\web-$WebPort.err.log")
} finally { $env:MONEYFEST_API_URL=$previousApi }
@{api_pid=$apiProcess.Id;web_pid=$webProcess.Id;api_port=$ApiPort;web_port=$WebPort} | ConvertTo-Json | Set-Content (Join-Path $projectRoot ".local\app-$WebPort.json")
$ready=$false
for ($attempt=0;$attempt -lt 30;$attempt++) {
    try {
        $health=Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 1
        $web=Invoke-WebRequest "http://127.0.0.1:$WebPort" -TimeoutSec 1
        if ($health.status -eq 'ok' -and $web.StatusCode -eq 200) { $ready=$true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if (!$ready) {
    & (Join-Path $PSScriptRoot 'stop-app.ps1') -WebPort $WebPort
    throw 'Application did not become ready. Inspect API and web logs in .local.'
}
Write-Output "MoneyFest ready at http://127.0.0.1:$WebPort (API :$ApiPort). Logs are in .local."
if ($Lan) {
    $lanAddress=Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -match '^192\.168\.|^10\.|^172\.(1[6-9]|2[0-9]|3[01])\.' -and $_.InterfaceAlias -notmatch 'vEthernet|Docker|WSL' } |
        Select-Object -First 1 -ExpandProperty IPAddress
    if ($lanAddress) { Write-Output "Open on a phone on the same Wi-Fi: http://${lanAddress}:$WebPort" }
    else { Write-Warning 'LAN mode is running, but no private IPv4 address was found.' }
}
