param([int]$WebPort=5174)
$projectRoot=Split-Path $PSScriptRoot -Parent
$statePath=Join-Path $projectRoot ".local\app-$WebPort.json"
if (!(Test-Path $statePath)) { Write-Output 'No recorded application processes.'; exit }
$state=Get-Content $statePath -Raw | ConvertFrom-Json
foreach ($processId in @($state.api_pid,$state.web_pid)) {
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine.IndexOf($projectRoot,[StringComparison]::OrdinalIgnoreCase) -ge 0 -and ($process.Name -in @('java.exe','node.exe'))) {
        Stop-Process -Id $processId
        Wait-Process -Id $processId -Timeout 10 -ErrorAction SilentlyContinue
    }
}
Remove-Item -LiteralPath $statePath
