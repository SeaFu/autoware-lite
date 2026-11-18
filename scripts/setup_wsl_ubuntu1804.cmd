@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title Autoware-Lite - Ubuntu 18.04 WSL2 Import

echo.
echo ============================================================
echo   Autoware-Lite - Ubuntu 18.04 WSL2 匯入精靈
echo ============================================================
echo.
echo 本工具會建立新的 WSL2 發行版，不會執行 wsl --unregister。
echo 必須先啟用 WSL2 並完成 Windows 必要的重新開機。
echo.

where wsl.exe >nul 2>&1
if errorlevel 1 goto :wsl_unavailable

wsl.exe --status
if errorlevel 1 goto :wsl_unavailable

set "DEFAULT_DIR=%USERPROFILE%\WSL\Autoware1804"
set "DEFAULT_NAME=Autoware-18.04"
set "DEFAULT_ROOTFS=%USERPROFILE%\Downloads\ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz"

echo.
echo [1/3] 請輸入 WSL2 發行版的安裝資料夾。
echo       範例：D:\WSL\Autoware1804
echo       直接按 Enter 使用預設路徑：%DEFAULT_DIR%
set "INSTALL_DIR="
set /p "INSTALL_DIR=安裝路徑："
if not defined INSTALL_DIR set "INSTALL_DIR=%DEFAULT_DIR%"
set "INSTALL_DIR=%INSTALL_DIR:"=%"
for %%I in ("%INSTALL_DIR%") do set "INSTALL_DIR=%%~fI"
if "%INSTALL_DIR:~0,2%"=="\\" goto :invalid_dir
for %%I in ("%INSTALL_DIR%") do if /i "%%~fI"=="%%~dI\" goto :invalid_dir
if exist "%INSTALL_DIR%" goto :check_existing_dir
goto :ask_name

:check_existing_dir
dir /b /a "%INSTALL_DIR%" 2>nul | findstr /r "." >nul
if not errorlevel 1 goto :nonempty_dir

:ask_name
echo.
echo [2/3] 請輸入新 WSL 發行版名稱。
echo       直接按 Enter 使用預設名稱：%DEFAULT_NAME%
set "DISTRO_NAME="
set /p "DISTRO_NAME=WSL 名稱："
if not defined DISTRO_NAME set "DISTRO_NAME=%DEFAULT_NAME%"
set "DISTRO_NAME=%DISTRO_NAME:"=%"
if not defined DISTRO_NAME goto :invalid_name

echo.
echo [3/3] 請輸入已下載的 Ubuntu 18.04 WSL rootfs 檔案路徑。
echo       直接按 Enter 使用預設檔案：%DEFAULT_ROOTFS%
set "ROOTFS_FILE="
set /p "ROOTFS_FILE=rootfs 檔案："
if not defined ROOTFS_FILE set "ROOTFS_FILE=%DEFAULT_ROOTFS%"
set "ROOTFS_FILE=%ROOTFS_FILE:"=%"
for %%I in ("%ROOTFS_FILE%") do set "ROOTFS_FILE=%%~fI"
if not exist "%ROOTFS_FILE%" goto :missing_rootfs
if exist "%ROOTFS_FILE%\NUL" goto :missing_rootfs

echo.
echo ===================== 請確認設定 ============================
echo   WSL 名稱       : "%DISTRO_NAME%"
echo   安裝資料夾     : "%INSTALL_DIR%"
echo   Ubuntu rootfs  : "%ROOTFS_FILE%"
echo ============================================================
echo.
echo 注意：如果這個 WSL 名稱已存在，wsl --import 會拒絕建立。
echo 本工具不會刪除既有的 WSL 發行版或安裝資料夾內容。
choice /C YN /N /M "確認開始匯入？ [Y/N] "
if errorlevel 2 goto :cancelled
if errorlevel 1 goto :import
goto :cancelled

:import
if exist "%INSTALL_DIR%" goto :run_import
mkdir "%INSTALL_DIR%"
if errorlevel 1 goto :create_dir_failed

:run_import
echo.
echo [執行中] 正在匯入 Ubuntu 18.04 WSL2，可能需要數分鐘...
wsl.exe --import "%DISTRO_NAME%" "%INSTALL_DIR%" "%ROOTFS_FILE%" --version 2
if errorlevel 1 goto :import_failed

echo.
echo [成功] 已完成 WSL2 發行版匯入：%DISTRO_NAME%
echo.
wsl.exe --list --verbose
echo.
echo 提醒：wsl --import 預設以 root 啟動。
echo 下一步請依 README 第 1.3 節建立 Linux 一般使用者。
echo.
choice /C YN /N /M "是否立即進入新安裝的 Ubuntu？ [Y/N] "
if errorlevel 2 goto :finished
if errorlevel 1 wsl.exe -d "%DISTRO_NAME%"
goto :finished

:wsl_unavailable
echo.
echo [錯誤] WSL2 尚未準備好，或 wsl --status 執行失敗。
echo 請先以系統管理員身分開啟 Windows CMD，執行：
echo   wsl --install --no-distribution
echo 依照提示重新開機，然後再次執行本工具。
goto :error_exit

:invalid_dir
echo.
echo [錯誤] 安裝位置必須是本機磁碟中的專用子資料夾，不能使用磁碟根目錄或網路分享路徑。
goto :error_exit

:nonempty_dir
echo.
echo [錯誤] 目標資料夾已存在且非空白："%INSTALL_DIR%"
echo 為避免混入或覆蓋既有資料，請重新執行並選擇空白資料夾。
goto :error_exit

:invalid_name
echo.
echo [錯誤] WSL 名稱不可為空。
goto :error_exit

:missing_rootfs
echo.
echo [錯誤] 找不到 rootfs 檔案："%ROOTFS_FILE%"
echo 請確認已下載 .tar.gz，且輸入的是實際檔案路徑。
goto :error_exit

:create_dir_failed
echo.
echo [錯誤] 無法建立資料夾："%INSTALL_DIR%"
echo 請確認磁碟存在、容量足夠且擁有寫入權限。
goto :error_exit

:import_failed
echo.
echo [錯誤] wsl --import 執行失敗。請查看上方 Windows/WSL 訊息。
echo 可能原因：名稱已存在、rootfs 無效、WSL2 未啟用、磁碟空間不足。
echo 注意：本工具不會自動刪除匯入過程建立的資料夾或任何 WSL 發行版。
goto :error_exit

:cancelled
echo.
echo [取消] 未執行 WSL 匯入。
goto :finished

:error_exit
echo.
echo [結束] 請修正上列問題後再重新執行。
echo 按任意鍵關閉...
pause >nul
exit /b 1

:finished
echo.
echo 按任意鍵結束安裝精靈...
pause >nul
exit /b 0
