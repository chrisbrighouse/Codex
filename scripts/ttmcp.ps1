#!/usr/bin/env pwsh
$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $repoRoot
if (Get-Command py -ErrorAction SilentlyContinue) {
  py -3 scripts/mcp_timetable_ctl.py @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  python scripts/mcp_timetable_ctl.py @args
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
  python3 scripts/mcp_timetable_ctl.py @args
} else {
  Write-Error 'Python not found on PATH. Install Python 3 or ensure py/python is available.'
}

