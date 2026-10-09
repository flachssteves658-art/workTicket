@echo off
setlocal

set "SystemRoot=C:\Windows"
set "windir=C:\Windows"
set "ComSpec=C:\Windows\System32\cmd.exe"

"C:\Windows\System32\setx.exe" SYSTEMROOT "C:\Windows" >nul
if errorlevel 1 goto :failed
"C:\Windows\System32\setx.exe" WINDIR "C:\Windows" >nul
if errorlevel 1 goto :failed
"C:\Windows\System32\setx.exe" COMSPEC "C:\Windows\System32\cmd.exe" >nul
if errorlevel 1 goto :failed

echo Codex Windows environment repaired successfully.
echo SYSTEMROOT=C:\Windows
echo WINDIR=C:\Windows
echo COMSPEC=C:\Windows\System32\cmd.exe
echo.
echo Completely exit Codex, then start it again so the new process inherits
echo the repaired environment.
pause
exit /b 0

:failed
echo Failed to write the current-user environment. Error code: %errorlevel%
pause
exit /b 1
