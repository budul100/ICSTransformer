@echo off
set SCRIPT_DIR=C:\Users\mgr\HiDrive\Software\Scripts\Termine

if "%~1"=="" (
    echo Drag an .ics file onto this script, or call it with a file path as argument.
    pause
    exit /b 1
)

set INPUT=%~1
set OUTPUT=%~dpn1_transformed.ics

python "%SCRIPT_DIR%\transform.py" "%INPUT%" "%OUTPUT%"

if %errorlevel%==0 (
    echo.
    echo Output: %OUTPUT%
) else (
    echo.
    echo Something went wrong.
)
pause
