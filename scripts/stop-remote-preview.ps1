$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$local=Join-Path $projectRoot '.local'
foreach ($entry in @(@{file='remote-preview.json';name='cloudflared.exe'},@{file='preview.json';name='node.exe'})) {
    $state=Join-Path $local $entry.file
    if (!(Test-Path $state)) { continue }
    $id=(Get-Content -LiteralPath $state -Raw | ConvertFrom-Json).pid
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if ($process -and $process.Name -eq $entry.name -and $process.CommandLine.IndexOf($projectRoot,[StringComparison]::OrdinalIgnoreCase) -ge 0) {
        Stop-Process -Id $id
    }
    Remove-Item -LiteralPath $state
}
