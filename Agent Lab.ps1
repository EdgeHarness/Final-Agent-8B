# Agent Lab launcher for Windows (incl. Snapdragon X Elite / arm64).
# Right-click > Run with PowerShell, or:  powershell -ExecutionPolicy Bypass -File ".\Agent Lab.ps1"
# Everything stays on this machine: the server binds loopback only.

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$py = $env:PYTHON
if (-not $py) { $py = 'python' }
if (-not (Get-Command $py -ErrorAction SilentlyContinue)) { $py = 'py' }
if (-not (Get-Command $py -ErrorAction SilentlyContinue)) {
  Write-Host 'No Python found. Install Python 3, then try again.'
  Read-Host 'Press Enter to close'; exit 1
}

& $py -c 'import requests, pptx, openpyxl' 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Installing the agent''s Python packages (one time)...'
  & $py -m pip install --quiet requests python-pptx openpyxl
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Install failed. Run:  $py -m pip install requests python-pptx openpyxl"
    Read-Host 'Press Enter to close'; exit 1
  }
}

# Optional: the app window. Uses the WebView2 runtime already present on Windows
# 11, so there is no bundled browser and nothing to compile for arm64.
& $py -c 'import webview' 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Installing pywebview for the app window (one time, optional)...'
  & $py -m pip install --quiet pywebview 2>$null
}

# The lab talks to a local Ollama on 11434.
try {
  Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 -UseBasicParsing | Out-Null
} catch {
  if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host 'Starting Ollama...'
    Start-Process -WindowStyle Hidden ollama 'serve'
    Start-Sleep -Seconds 2
  }
}

& $py -m webui.app
