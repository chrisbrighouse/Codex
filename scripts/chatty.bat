@echo off
setlocal
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%\..

REM Auto-start Timetable MCP if not running
call "%SCRIPT_DIR%ttmcp.bat" status >nul 2>&1
if errorlevel 1 (
  echo Starting Timetable MCP...
  call "%SCRIPT_DIR%ttmcp.bat" start >nul 2>&1
  REM tiny delay
  ping -n 2 127.0.0.1 >nul
)

REM Auto-start Geo MCP if not running
call "%SCRIPT_DIR%gmcp.bat" status >nul 2>&1
if errorlevel 1 (
  echo Starting Geo MCP...
  call "%SCRIPT_DIR%gmcp.bat" start >nul 2>&1
  ping -n 2 127.0.0.1 >nul
)

py -3 -m src.main %*
