param([Parameter(Mandatory=$true)][string]$AllowedEmail)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$local=Join-Path $projectRoot '.local'
$cloudflared=Join-Path $local 'cloudflared.exe'
$state=Join-Path $local 'remote-preview.json'
if ($AllowedEmail -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') { throw 'Enter one complete email address.' }
if (!(Test-Path $cloudflared)) { throw 'Download the current cloudflared Windows binary from the official Cloudflare release into .local/cloudflared.exe.' }
if (Test-Path $state) { throw 'A remote preview is already recorded. Stop it first.' }
if (!(Get-NetTCPConnection -LocalPort 4173 -State Listen -ErrorAction SilentlyContinue)) { & (Join-Path $PSScriptRoot 'start-preview.ps1') }
$out=Join-Path $local 'remote-preview.log'
$err=Join-Path $local 'remote-preview.err.log'
$process=Start-Process -FilePath $cloudflared -ArgumentList @('tunnel','--no-autoupdate','--url','http://127.0.0.1:4173','--allowed-mail',$AllowedEmail) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
@{pid=$process.Id;email=$AllowedEmail} | ConvertTo-Json | Set-Content -LiteralPath $state
for ($attempt=0;$attempt -lt 60;$attempt++) {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) { throw 'Cloudflare Tunnel stopped. Inspect .local/remote-preview.err.log.' }
    $log=(Get-Content -LiteralPath $err -Raw -ErrorAction SilentlyContinue) + (Get-Content -LiteralPath $out -Raw -ErrorAction SilentlyContinue)
    $match=[regex]::Match($log,'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($match.Success) {
        Write-Output "Protected mobile preview: $($match.Value)"
        Write-Output "One-time email gate: $AllowedEmail"
        return
    }
}
throw 'The tunnel URL did not appear. Inspect .local/remote-preview.err.log.'
