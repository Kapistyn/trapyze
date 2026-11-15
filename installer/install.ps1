# traPYze installer for Windows.
# Paste this line into PowerShell (no administrator needed):
#   irm https://github.com/kapistyn/trapyze/releases/latest/download/install.ps1 | iex
#
# What it does, all inside your own user account:
#   1. installs uv (by Astral), which fetches and runs Python for traPYze, if it isn't there yet
#   2. installs the newest traPYze from its GitHub releases, with its own window and tray icon
#   3. makes shortcuts on the desktop and in the Start menu, and opens traPYze
# Running it again updates traPYze. Your tools, results, plans and vault are never touched.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Repo = 'kapistyn/trapyze'

function Say($text) { Write-Host "  $text" }
function Fail($text) {
    Write-Host ""
    Write-Host "  $text" -ForegroundColor Red
    Write-Host "  Nothing else was changed. Questions: https://github.com/$Repo/issues" -ForegroundColor Red
    if ($env:TRAPYZE_SETUP_EXE) { Read-Host "  Press Enter to close" | Out-Null }
    exit 1
}

Write-Host ""
Write-Host "  traPYze installer" -ForegroundColor Cyan
Write-Host ""

# 1. uv ---------------------------------------------------------------------
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    Say "Installing uv, which runs Python for traPYze (about 30 MB)..."
    try {
        $env:UV_NO_MODIFY_PATH = $null
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch { Fail "uv couldn't be installed: $($_.Exception.Message)" }
    $uv = @("$env:USERPROFILE\.local\bin\uv.exe", "$env:LOCALAPPDATA\Programs\uv\uv.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $uv) { Fail "uv was installed but can't be found. Close this window, open a new PowerShell and try again." }
}
Say "Using uv at $uv"

# 2. The newest release -----------------------------------------------------
$source = $env:TRAPYZE_WHEEL   # set this to a local .whl file to install a build of your own
if (-not $source) {
    try {
        $release = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ 'User-Agent' = 'traPYze-installer' }
    } catch { Fail "Couldn't ask GitHub for the newest version. Check the internet connection. ($($_.Exception.Message))" }
    $source = ($release.assets | Where-Object { $_.name -like '*.whl' } | Select-Object -First 1).browser_download_url
    if (-not $source) { Fail "The newest release has no file to install." }
    Say "Newest version: $($release.tag_name)"
}

# 3. Close a traPYze that is open (Windows can't replace a program in use) -----
$open = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'trapyze' -and $_.ProcessId -ne $PID -and $_.Name -notmatch 'powershell|pwsh' }
if ($open) {
    Say "Closing the traPYze that is open..."
    $open | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

# 4. Install ------------------------------------------------------------------
Say "Installing traPYze (the first time takes a minute or two)..."
& $uv tool install --reinstall --python 3.12 "trapyze[desktop] @ $source"
if ($LASTEXITCODE -ne 0) { Fail "Installing traPYze didn't work; the lines above say why." }
& $uv tool update-shell *> $null
$bin = (& $uv tool dir --bin).Trim()
$trapyze = Join-Path $bin 'trapyze.exe'
if (-not (Test-Path $trapyze)) { Fail "traPYze was installed but can't be found in $bin." }

# 5. Shortcuts, then open it ----------------------------------------------------
& $trapyze shortcut
Write-Host ""
Write-Host "  Done. traPYze is opening; next time, use the shortcut on your desktop." -ForegroundColor Green
Write-Host "  Your tools live in: $env:USERPROFILE\Trapyze"
Write-Host ""
Start-Process (Join-Path $bin 'trapyze-app.exe')
