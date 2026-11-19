@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Autoware-Lite - Ubuntu 18.04 WSL2 Import

rem Self-contained wizard: this CMD launcher runs the embedded PowerShell code.
rem Keep the launcher ASCII so CMD never needs to parse Chinese prompt text.
set "AWL_WIZARD_SELF=%~f0"
where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Windows PowerShell was not found.
    pause
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -Command "$src = [IO.File]::ReadAllText($env:AWL_WIZARD_SELF, [Text.Encoding]::UTF8); $tag = ':AWL_PS_PAYLOAD_START'; $at = $src.LastIndexOf($tag); if ($at -lt 0) { throw 'Installer payload is missing.' }; & ([scriptblock]::Create($src.Substring($at + $tag.Length)))"
set "AWL_WIZARD_RESULT=%ERRORLEVEL%"
echo.
echo Press any key to close this window...
pause >nul
exit /b %AWL_WIZARD_RESULT%

:AWL_PS_PAYLOAD_START
$ErrorActionPreference = 'Stop'

function Show-Info([string] $message) {
    Write-Host ('[資訊] ' + $message) -ForegroundColor Cyan
}
function Show-OK([string] $message) {
    Write-Host ('[成功] ' + $message) -ForegroundColor Green
}
function Show-Warning([string] $message) {
    Write-Host ('[提醒] ' + $message) -ForegroundColor Yellow
}
function Ask-Default([string] $label, [string] $defaultValue) {
    Write-Host ('預設值：' + $defaultValue)
    $answer = Read-Host ($label + '（直接按 Enter 使用預設值）')
    if ([string]::IsNullOrWhiteSpace($answer)) { return $defaultValue }
    return $answer
}

function Normalize-LocalPath([string] $rawPath, [string] $description) {
    $candidate = $rawPath.Trim()
    # Windows Explorer's "Copy as path" adds one pair of outer quotes.
    if ($candidate.Length -ge 2 -and $candidate.StartsWith('"') -and $candidate.EndsWith('"')) {
        $candidate = $candidate.Substring(1, $candidate.Length - 2).Trim()
    }
    if ([string]::IsNullOrWhiteSpace($candidate) -or $candidate.Contains('"')) {
        throw ($description + '包含不完整或多餘的雙引號，請重新複製完整路徑。')
    }
    $candidate = [Environment]::ExpandEnvironmentVariables($candidate)
    if ($candidate -notmatch '^[A-Za-z]:[\\/]') {
        throw ($description + '必須是完整的本機磁碟路徑，例如 D:\WSL\Autoware1804；不接受網路分享路徑。')
    }
    try { return [IO.Path]::GetFullPath($candidate) }
    catch { throw ($description + '不是有效的路徑：' + $_.Exception.Message) }
}

function Get-RegisteredNames {
    # A brand-new WSL installation can return a nonzero exit code here.
    try {
        $lines = @(& wsl.exe --list --quiet 2>$null)
        if ($LASTEXITCODE -ne 0) { return }
        foreach ($line in $lines) {
            $clean = (([string] $line) -replace '[\x00\uFEFF]', '').Trim()
            if ($clean.Length -gt 0) { Write-Output $clean }
        }
    }
    catch { } # The import itself is the final authority.
}

function Test-EmptyFolder([string] $folder) {
    if (-not (Test-Path -LiteralPath $folder)) { return $true }
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) {
        throw ('安裝位置已被檔案占用：' + $folder)
    }
    $child = @(Get-ChildItem -LiteralPath $folder -Force -ErrorAction Stop | Select-Object -First 1)
    if ($child.Count -gt 0) {
        throw ('安裝資料夾已有內容；為保護既有資料，請改選空白資料夾：' + $folder)
    }
    return $true
}

try {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '   Autoware-Lite | Ubuntu 18.04 WSL2 匯入精靈' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '本精靈只建立 Ubuntu 18.04 WSL2 發行版，不安裝 ROS 或 Autoware。'
    Write-Host '不會刪除既有 WSL 發行版，也不會執行 wsl --unregister。'
    Write-Host ''

    Write-Host '[環境檢查] 檢查 Windows 是否可以使用 WSL...' -ForegroundColor White
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        throw '找不到 wsl.exe。請先依 README 1.1 安裝 WSL2，完成重新開機後再執行。'
    }
    Show-OK '已找到 WSL 指令。'
    try {
        & wsl.exe --status >$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            Show-OK 'WSL 狀態指令可正常執行。'
        }
        else {
            Show-Warning '無法由 wsl --status 確認完整狀態；尚無 Linux 發行版時可能出現提示，仍可嘗試首次匯入。'
        }
    }
    catch { Show-Warning '無法由 wsl --status 確認完整狀態；將以實際匯入結果判定。' }
    $registered = @(Get-RegisteredNames)
    if ($registered.Count -eq 0) {
        Show-Info '尚未偵測到已匯入的發行版；全新電腦出現此情況是正常的。'
    }
    else { Show-Info ('已偵測到的發行版：' + ($registered -join ', ')) }

    $userProfile = [Environment]::GetFolderPath('UserProfile')
    $defaultFolder = Join-Path $userProfile 'WSL\Autoware1804'
    $defaultName = 'Autoware-18.04'
    $defaultRootfs = Join-Path $userProfile 'Downloads\ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz'

    Write-Host ''
    Write-Host '[1/3] 指定 Ubuntu 18.04 WSL2 的安裝資料夾' -ForegroundColor White
    Show-Info '沒有特別需求，直接按 Enter 即可；也可以指定 D:\WSL\Autoware1804。'
    while ($true) {
        $inputFolder = Ask-Default 'WSL2 安裝資料夾' $defaultFolder
        try {
            $installFolder = Normalize-LocalPath $inputFolder '安裝資料夾'
            $root = [IO.Path]::GetPathRoot($installFolder)
            if ($installFolder -ieq $root) {
                throw '不能把整個磁碟根目錄當成 WSL 安裝資料夾，請指定專用子資料夾。'
            }
            $null = Test-EmptyFolder $installFolder
            Show-OK ('安裝資料夾可使用：' + $installFolder)
            break
        }
        catch {
            Show-Warning $_.Exception.Message
            Show-Info '請輸入其他資料夾；按 Ctrl+C 可取消安裝。'
        }
    }

    Write-Host ''
    Write-Host '[2/3] 指定 WSL 發行版名稱' -ForegroundColor White
    Show-Info '建議直接按 Enter 使用 Autoware-18.04，以便照 README 複製後續指令。'
    while ($true) {
        $distributionName = (Ask-Default 'WSL 發行版名稱' $defaultName).Trim()
        if ($distributionName -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') {
            Show-Warning '名稱只允許英文字母、數字、句點、底線與連字號，且不能為空白。'
            continue
        }
        if (@($registered | Where-Object { $_ -ieq $distributionName }).Count -gt 0) {
            Show-Warning ('名稱 ' + $distributionName + ' 已存在，請勿重複匯入或覆蓋。')
            Show-Info ('若它就是要使用的系統，請關閉精靈並在 Windows CMD 執行：wsl -d ' + $distributionName)
            Show-Info '若要另外建立一份，請輸入不同的名稱。'
            continue
        }
        Show-OK ('發行版名稱可使用：' + $distributionName)
        break
    }

    Write-Host ''
    Write-Host '[3/3] 指定 Ubuntu 18.04 rootfs 壓縮檔' -ForegroundColor White
    Show-Info '檔案若放在 Windows Downloads 且名稱未修改，直接按 Enter。'
    Show-Info '也可在檔案總管右鍵「複製路徑」後貼上；外層雙引號會自動處理。'
    while ($true) {
        $inputRootfs = Ask-Default 'Ubuntu rootfs 檔案' $defaultRootfs
        try {
            $rootfsPath = Normalize-LocalPath $inputRootfs 'rootfs 檔案'
            if (-not (Test-Path -LiteralPath $rootfsPath -PathType Leaf)) {
                throw ('找不到檔案：' + $rootfsPath)
            }
            if ($rootfsPath -notmatch '(?i)\.(tar|tar\.gz|tgz)$') {
                throw '請選擇 Ubuntu WSL rootfs 的 .tar、.tar.gz 或 .tgz 檔案。'
            }
            $rootfsFile = Get-Item -LiteralPath $rootfsPath -ErrorAction Stop
            if ($rootfsFile.Length -lt 1024) {
                throw 'rootfs 檔案大小異常，請確認不是未下載完成的檔案。'
            }
            Show-OK ('已找到 rootfs 檔案：' + $rootfsPath)
            break
        }
        catch {
            Show-Warning $_.Exception.Message
            Show-Info '請確認檔案位置後重新貼上路徑；按 Ctrl+C 可取消安裝。'
        }
    }

    Write-Host ''
    Write-Host '======================== 安裝摘要 ========================' -ForegroundColor Cyan
    Write-Host ('WSL 發行版名稱 : ' + $distributionName)
    Write-Host ('WSL 安裝資料夾 : ' + $installFolder)
    Write-Host ('Ubuntu rootfs   : ' + $rootfsPath)
    Write-Host 'WSL 版本        : 2'
    Write-Host '==========================================================' -ForegroundColor Cyan
    Show-Info '只有輸入 Y 才會開始匯入；按 Enter 或輸入 N 會取消。'
    $confirm = (Read-Host '確定開始匯入？[Y/N]').Trim()
    if ($confirm -ine 'Y') {
        Show-Info '已取消，沒有執行 WSL 匯入。'
        exit 0
    }

    # Recheck before writing. Never unregister or remove an existing distribution.
    $null = Test-EmptyFolder $installFolder
    if (@(Get-RegisteredNames | Where-Object { $_ -ieq $distributionName }).Count -gt 0) {
        throw ('發行版名稱已存在：' + $distributionName + '。未進行匯入。')
    }
    if (-not (Test-Path -LiteralPath $installFolder)) {
        $null = New-Item -ItemType Directory -Path $installFolder -Force -ErrorAction Stop
    }

    Write-Host ''
    Show-Info '正在執行 wsl --import，可能需要數分鐘，請勿關閉視窗。'
    & wsl.exe --import $distributionName $installFolder $rootfsPath --version 2
    if ($LASTEXITCODE -ne 0) {
        throw ('wsl --import 失敗（結束代碼 ' + $LASTEXITCODE + '）。請查看上方 WSL 錯誤訊息。')
    }
    Show-OK ('已匯入 WSL2 發行版：' + $distributionName)
    Write-Host ''
    & wsl.exe --list --verbose
    Write-Host ''

    Show-Info '正在檢查新系統的 Ubuntu 版本...'
    $versionVerified = $false
    try {
        $osLines = @(& wsl.exe -d $distributionName --exec /bin/cat /etc/os-release 2>$null)
        $osExit = $LASTEXITCODE
        if ($osExit -eq 0 -and @($osLines | Where-Object { $_ -match '^VERSION_ID="?18\.04"?$' }).Count -gt 0) {
            $versionVerified = $true
            Show-OK 'Ubuntu 版本為 18.04，可以繼續 README 第 1.3 節。'
        }
        elseif ($osExit -eq 0) {
            Show-Warning '發行版已匯入，但檢查結果不是 Ubuntu 18.04；請先確認 rootfs 版本。'
            $osLines | Where-Object { $_ -match '^(NAME|VERSION_ID)=' } | ForEach-Object { Write-Host $_ }
        }
        else { Show-Warning '發行版已匯入，但尚未成功讀取 /etc/os-release，請手動檢查。' }
    }
    catch { Show-Warning '發行版已匯入，但無法自動確認 Ubuntu 版本，請依 README 手動檢查。' }

    Write-Host ''
    if ($versionVerified) {
        Write-Host '下一步：依 README 第 1.3 節建立 Linux 一般使用者，再安裝 ROS Melodic。'
    }
    else {
        Show-Warning ('請先在 Windows CMD 執行：wsl -d ' + $distributionName + ' -- cat /etc/os-release')
        Show-Warning '確認 VERSION_ID 為 18.04 後再進行 ROS 安裝。'
    }
    Write-Host '注意：匯入精靈不會安裝 ROS、Autoware，也不會修改既有發行版。'
    $launch = (Read-Host '是否現在開啟 Ubuntu？[Y/N]（按 Enter 表示 N）').Trim()
    if ($launch -ieq 'Y') { & wsl.exe -d $distributionName }
    exit 0
}
catch {
    Write-Host ''
    Write-Host ('[錯誤] ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host '請確認 WSL2 已啟用並完成重新開機，且 rootfs 與安裝資料夾正確。'
    Write-Host '可在 Windows CMD 執行 wsl --status 與 wsl --list --verbose 查看狀態。'
    Write-Host '本精靈不會自動刪除任何 WSL 發行版或資料夾。'
    exit 1
}
