@echo off
setlocal DisableDelayedExpansion
rem Use existing runtimes only, including when py.exe is Python Install Manager.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
set "PYLAUNCHER_ALLOW_INSTALL="
set "PYLAUNCHER_ALWAYS_INSTALL="
rem Resolve real executable names through PATH. Calling bare py or python here
rem would also search the current folder and consider batch wrappers.
for %%I in (py.exe) do set "FIRE_PY=%%~$PATH:I"
for %%I in (python.exe) do set "FIRE_PYTHON=%%~$PATH:I"
if /i "%FIRE_PY%"=="%~dp0py.exe" set "FIRE_PY="
if /i "%FIRE_PYTHON%"=="%~dp0python.exe" set "FIRE_PYTHON="
if /i "%FIRE_PY%"=="%CD%\py.exe" set "FIRE_PY="
if /i "%FIRE_PYTHON%"=="%CD%\python.exe" set "FIRE_PYTHON="
if not defined FIRE_PY goto check_python
"%FIRE_PY%" -3 -I -S -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto run_py

:check_python
if not defined FIRE_PYTHON goto missing
"%FIRE_PYTHON%" -I -S -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto run_python

:missing
echo Python 3.11 or later is required. Install Python with Tcl/Tk support from python.org.
exit /b 1

:run_py
"%FIRE_PY%" -3 -I -S "%~dp0open_fire_toolkit\__main__.py" %*
goto finished

:run_python
"%FIRE_PYTHON%" -I -S "%~dp0open_fire_toolkit\__main__.py" %*

:finished
set "TOOLKIT_EXIT_CODE=%ERRORLEVEL%"
exit /b %TOOLKIT_EXIT_CODE%
