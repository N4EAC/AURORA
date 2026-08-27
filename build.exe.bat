@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not defined AURORA_VERSION set "AURORA_VERSION=0.1.0"
if not defined PYTHON_BIN set "PYTHON_BIN=py -3"
set "BUILD_VENV=%CD%\.venv-build-windows"
set "PYINSTALLER_CONFIG_DIR=%CD%\build\pyinstaller-config-windows"
set "BUILD_STAGE=output directory creation"
if not exist "dist\installer" mkdir "dist\installer"
if errorlevel 1 goto :error
if not exist "build" mkdir "build"
if errorlevel 1 goto :error

set "BUILD_STAGE=build preflight"
%PYTHON_BIN% packaging\build_preflight.py Windows "%AURORA_VERSION%"
if errorlevel 1 goto :error
set "BUILD_STAGE=virtual environment creation"
%PYTHON_BIN% -m venv "%BUILD_VENV%"
if errorlevel 1 goto :error
set "BUILD_STAGE=Python build dependencies"
"%BUILD_VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%BUILD_VENV%\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :error
if not "%AURORA_SKIP_TESTS%"=="1" (
    set "BUILD_STAGE=test suite"
    set "QT_QPA_PLATFORM=offscreen"
    "%BUILD_VENV%\Scripts\python.exe" -m unittest discover -s tests -q
    if errorlevel 1 goto :error
)

set "BUILD_STAGE=build metadata and bundled Hamlib"
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
set "BUILD_STAGE=PyInstaller application"
"%BUILD_VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath "%CD%\dist" --workpath "%CD%\build\pyinstaller-windows" "%CD%\packaging\aurora.spec"
if errorlevel 1 goto :error
if not exist "dist\Aurora\Aurora.exe" (
    echo ERROR: PyInstaller did not create dist\Aurora\Aurora.exe.
    goto :error
)
"%BUILD_VENV%\Scripts\python.exe" packaging\verify_bundle.py "%CD%\dist\Aurora"
if errorlevel 1 goto :error

set "BUILD_STAGE=Inno Setup discovery"
if defined ISCC_EXE set "ISCC=%ISCC_EXE%"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo ERROR: Inno Setup 6 was not found. Set ISCC_EXE to ISCC.exe.
    goto :error
)
set "BUILD_STAGE=Inno Setup installer"
"%ISCC%" /DMyAppVersion=%AURORA_VERSION% packaging\windows\Aurora.iss
if errorlevel 1 goto :error
if not exist "dist\installer\Aurora-%AURORA_VERSION%-windows-x86_64-setup.exe" (
    echo ERROR: Inno Setup did not create the expected installer.
    goto :error
)
set "BUILD_STAGE=complete"
echo Build complete: dist\Aurora\Aurora.exe
echo Installer complete: dist\installer\Aurora-%AURORA_VERSION%-windows-x86_64-setup.exe
exit /b 0

:error
set "BUILD_EXIT=%ERRORLEVEL%"
if "%BUILD_EXIT%"=="0" set "BUILD_EXIT=1"
echo ERROR: Aurora Windows build failed during %BUILD_STAGE% ^(exit %BUILD_EXIT%^).
echo Output root: %CD%\dist
exit /b %BUILD_EXIT%
