@echo off
setlocal
pushd "%~dp0" || exit /b 1
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto run_py
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto run_python
echo Python 3.11 or later is required. Install Python with Tcl/Tk support from python.org.
popd
exit /b 1

:run_py
py -3 -m open_fire_toolkit %*
goto finished

:run_python
python -m open_fire_toolkit %*

:finished
set "TOOLKIT_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %TOOLKIT_EXIT_CODE%
