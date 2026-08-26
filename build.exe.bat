@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not defined AURORA_VERSION set "AURORA_VERSION=0.1.0"
if not defined PYTHON_BIN set "PYTHON_BIN=py -3"
set "BUILD_VENV=%CD%\.venv-build-windows"
set "PYINSTALLER_CONFIG_DIR=%CD%\build\pyinstaller-config-windows"

%PYTHON_BIN% -m venv "%BUILD_VENV%"
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :error
if not "%AURORA_SKIP_TESTS%"=="1" (
    set "QT_QPA_PLATFORM=offscreen"
    "%BUILD_VENV%\Scripts\python.exe" -m unittest discover -s tests -q
    if errorlevel 1 goto :error
)

"%BUILD_VENV%\Scripts\python.exe" packaging\prepare_build.py "%AURORA_VERSION%"
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\python.exe" packaging\validate_operator_configuration.py
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\python.exe" tools\bootstrap_hamlib.py
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\python.exe" packaging\stage_hamlib.py
if errorlevel 1 goto :error
if exist "build\pyinstaller-windows" rmdir /s /q "build\pyinstaller-windows"
if exist "dist\Aurora" rmdir /s /q "dist\Aurora"
"%BUILD_VENV%\Scripts\pyinstaller.exe" --noconfirm --clean --distpath dist --workpath build\pyinstaller-windows packaging\aurora.spec
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\python.exe" packaging\verify_bundle.py dist\Aurora
if errorlevel 1 goto :error

if defined ISCC_EXE set "ISCC=%ISCC_EXE%"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo ERROR: Inno Setup 6 was not found. Set ISCC_EXE to ISCC.exe.
    goto :error
)
"%ISCC%" /DMyAppVersion=%AURORA_VERSION% packaging\windows\Aurora.iss
if errorlevel 1 goto :error
echo Build complete: dist\Aurora\Aurora.exe
echo Installer complete: dist\installer\Aurora-%AURORA_VERSION%-windows-x86_64-setup.exe
exit /b 0

:error
echo Aurora build failed.
exit /b 1
