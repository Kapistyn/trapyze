# Removes traPYze from Windows. Your home folder (tools, results, vault) stays,
# unless you delete it yourself afterwards.
$ErrorActionPreference = 'Continue'
Write-Host ""
Write-Host "  Removing traPYze" -ForegroundColor Cyan
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = @("$env:USERPROFILE\.local\bin\uv.exe", "$env:LOCALAPPDATA\Programs\uv\uv.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1 }
$bin = if ($uv) { (& $uv tool dir --bin).Trim() } else { "$env:USERPROFILE\.local\bin" }
$trapyze = Join-Path $bin 'trapyze.exe'

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'trapyze' -and $_.ProcessId -ne $PID -and $_.Name -notmatch 'powershell|pwsh' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

if (Test-Path $trapyze) {
    Write-Host "  Taking plans out of Task Scheduler..."
    & $trapyze schedule remove-all
}
foreach ($place in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
    Remove-Item (Join-Path $place 'traPYze.lnk') -ErrorAction SilentlyContinue
}
if ($uv) { & $uv tool uninstall trapyze }
Write-Host ""
Write-Host "  traPYze is removed. Your tools, results and vault are still in $env:USERPROFILE\Trapyze;" -ForegroundColor Green
Write-Host "  delete that folder yourself if you don't need them any more. uv stays installed for other programs."
Write-Host ""
