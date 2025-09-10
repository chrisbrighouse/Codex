#!/usr/bin/env pwsh
$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $repoRoot

# Auto-start Timetable MCP if not running
$tt = Join-Path $PSScriptRoot 'ttmcp.ps1'
& $tt 'status' | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Starting Timetable MCP...'
  & $tt 'start' | Out-Null
  Start-Sleep -Milliseconds 200
}

# Auto-start Geo MCP if not running
$gm = Join-Path $PSScriptRoot 'gmcp.ps1'
& $gm 'status' | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Starting Geo MCP...'
  & $gm 'start' | Out-Null
  Start-Sleep -Milliseconds 200
}

if (Get-Command py -ErrorAction SilentlyContinue) {
  py -3 -m src.main @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  python -m src.main @args
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
  python3 -m src.main @args
} else {
  Write-Error 'Python not found on PATH. Install Python 3 or ensure py/python is available.'
}
