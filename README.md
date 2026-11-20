# Autoware-Lite: Lightweight Autoware.AI Framework for Mapping and Navigation

**基於 Autoware.AI 1.14.0 的非官方精簡教學專案。**

本文件整理從 **Windows 11 → WSL2 Ubuntu 18.04 → ROS Melodic → Autoware.AI → PyQt5 GUI** 的完整操作流程。

以下功能以 Hunter／VLP-16 錄製資料進行離線驗證：

- **NDT Mapping**：播放 ROS bag、建立與匯出 PCD 地圖。

- **NDT Matching**：使用 PCD 對 bag 點雲定位，記錄 NDT 位姿與統計 CSV。

- **Waypoint**：從定位軌跡產生、檢查及載入 Autoware Waypoint CSV。

- **Pure Pursuit + Twist Filter**：從離線路徑產生速度與角速度命令，在 RViz 檢視目標點、搜尋圓與路徑。

> [!WARNING]
> **本專案只驗證 `/offline_nav/*` 的離線指令產生。**
>
> 沒有接 Hunter 車體控制，也沒有障礙物避讓／急停功能，不等於具備實車自主導航能力。
>
> **請勿將離線輸出直接接到馬達控制器。**

### 文件導覽

1. [環境與版本](#0-相容環境與注意事項)
2. [WSL2 與 Ubuntu 18.04 安裝](#1-windows建立-ubuntu-1804-wsl2)
3. [ROS Melodic 安裝](#2-ubuntu安裝-ros-melodic)
4. [Autoware.AI 編譯](#3-安裝-autowareai-1140只編譯需要的套件)
5. [啟動 GUI](#4-執行學生版-gui)
6. [離線驗證](#5-端到端離線驗證流程)
7. [常見問題](#6-常見故障與修正)
8. [本機版本記錄](#7-保留目前的-autowareai-版本和修改)

## 專案內容與來源

```text
autoware-lite/                       # https://github.com/SeaFu/autoware-lite
├── README.md                        # 安裝與端到端驗證（本文件）
├── Autoware_GUI/
│   ├── autoware_student_gui.py       # Python 3 / PyQt5 GUI
│   ├── aw_gui_core.py                # 啟動命令及資料處理
│   ├── convert_ndt_to_waypoints.py   # 軌跡 CSV → Waypoint CSV
│   ├── offline_nav_bridge.py        # Python 2 / rospy bridge
│   ├── launch/offline_pure_pursuit.launch
│   ├── rviz/{mapping,matching,navigation}.rviz
│   ├── tests/
│   └── README.md                     # GUI 逐頁操作說明
├── manifests/autoware_minimal.repos # 所需上游原始碼及 1.14.0 tag
├── scripts/setup_wsl_ubuntu1804.cmd # Windows 雙擊執行；內含 PowerShell 匯入精靈
├── scripts/capture_autoware_state.sh
└── .gitignore
```

**關於 `autoware.ai` 原始碼**

它是 Autoware Foundation 的第三方開源專案，**不是**這個 GUI 的自有程式。本倉庫以 `.repos` 清單記錄來源及版本，不重複上傳完整上游原始碼或編譯產物。

若你的 WSL 已修改任何 Autoware C++ 檔案，請先依後面的「記錄本機版本／修改」另存補丁；僅從 tag 重建不會包含這些修改。

## 0. 相容環境與注意事項

| 項目 | 版本／用途 |
| --- | --- |
| Windows | Windows 11（CMD／PowerShell + WSL2） |
| Linux | WSL2 Ubuntu **18.04 Bionic**，發行版名稱範例 `Autoware-18.04` |
| ROS | ROS 1 **Melodic**（主要 ROS 節點用 Python 2） |
| Autoware | **Autoware.AI 1.14.0**，選擇性編譯 `lidar_localizer` 與必要導航節點 |
| GUI | Python 3 + `python3-pyqt5`；RViz 需可用的 Linux 圖形介面 |
| 資料 | VLP-16 `sensor_msgs/PointCloud2` ROS bag（範例 `/points_raw`） |

> [!CAUTION]
> **以下使用的是已停止一般維護的舊版環境。**
>
> Ubuntu 18.04 的一般支援已於 2023 年結束、ROS Melodic 已 EOL，Autoware.AI 亦已封存。
>
> 套件來源、金鑰及依賴可能改變。請在每個步驟確認執行結果；建議在隔離的 WSL／教學主機使用，勿作公開網路服務。

## 1. Windows：建立 Ubuntu 18.04 WSL2

### 1.1 啟用 WSL2（Windows CMD）

這一節的指令都在 **Windows 11** 執行，**不是 Ubuntu 終端機**。

如果你的電腦已能正常使用 WSL2，可以直接前往 [1.2 匯入 Ubuntu 18.04](#12-匯入-ubuntu-1804-rootfs推薦使用-cmd-精靈)，不必重複安裝。

> [!IMPORTANT]
> **WSL2 啟用方式二選一：**
>
> - **方式 A（推薦）**：使用 WSL 安裝指令。
> - **方式 B**：只有方式 A 不支援或執行失敗時，才手動啟用 Windows 功能。
>
> **成功完成其中一種方式，就不要再執行另一種。**

#### 方式 A：使用 WSL 安裝指令（推薦）

1. 在 Windows 開始功能表搜尋 **`cmd`**。
2. 對「命令提示字元」按右鍵，選擇 **「以系統管理員身分執行」**。
3. 複製下方這一行，貼入 CMD 並按 Enter：

```bat
wsl --install --no-distribution
```

這個指令會準備 WSL 所需元件，**不會額外安裝 Microsoft Store 的預設 Ubuntu**。

等待指令完成。不同 Windows 版本的顯示訊息可能不同；**沒有安裝失敗／錯誤代碼**，且指令已返回 `C:\...` 提示符號，表示這一步已執行完畢。

**如果 Windows 要求重新開機，務必先重新開機再繼續。**若電腦正在等待重新啟動，先不要執行匯入精靈。

#### 方式 B：手動開啟 Windows 功能（只在方式 A 不可用時執行）

若方式 A 顯示不支援的參數或啟用失敗，可依 [Microsoft WSL 手動安裝步驟](https://learn.microsoft.com/windows/wsl/install-manual)，在**系統管理員 CMD** 依序執行下方兩個指令。

**先執行第一行，等待完成，再執行第二行：**

```bat
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

每一行應看到類似 `The operation completed successfully` 或「操作順利完成」。

**兩行都成功後重新開機。**如果方式 A 已成功，就不用再執行這兩行。

#### 確認 WSL2 已準備好

重新開機後，開啟 **Windows CMD（一般權限即可）**，依序完成下面三項檢查。

**① 更新 WSL：**

```bat
wsl --update
```

**② 將 WSL2 設為預設：**

```bat
wsl --set-default-version 2
```

**③ 查看 WSL 狀態：**

```bat
wsl --status
```

**成功判斷：**

- `wsl --update`：等待更新完成；若網路或更新服務有問題，依畫面錯誤訊息處理。

- `wsl --set-default-version 2`：應看到「操作順利完成」或同等成功訊息。

- `wsl --status`：若顯示「預設版本：2」（或 `Default Version: 2`），表示預設為 WSL2。

> [!TIP]
> **全新電腦尚未有 Linux 發行版是正常的。**
>
> 如果執行 `wsl --list --verbose` 顯示「沒有已安裝的發行版」，不代表出錯；Ubuntu 18.04 正是下一節才會建立。
>
> 若 Windows 提示 WSL 核心／虛擬化未啟用，請先處理該錯誤並完成必要的重新開機。

### 1.2 匯入 Ubuntu 18.04 rootfs（推薦使用 CMD 精靈）

> [!IMPORTANT]
> **本節的「CMD 安裝精靈」和「PowerShell 手動匯入」是二選一，不是連續步驟。**
>
> 1. 先在 **Windows CMD** 執行 `wsl --list --verbose`，確認是否已有 `Autoware-18.04`。
>
> 2. 如果已顯示 `Autoware-18.04`，且 `VERSION` 為 `2`，**直接前往 [1.3 建立 Linux 使用者](#13-建立-linux-使用者)**；不要重複匯入。
>
> 3. 若尚未匯入，選擇 **方式 A（推薦）** 或 **方式 B（手動）** 即可。完成其中一種後，不用再執行另一種。

先確認 Windows 是否已有 Ubuntu 18.04 的 rootfs 檔案。

如果沒有，請下載課程簡報採用的 [Ubuntu 18.04 WSL rootfs](https://cloud-images.ubuntu.com/releases/bionic/release/ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz)，建議存到 Windows **「下載」(Downloads)** 資料夾。

檔名通常是 `ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz`。

**這是壓縮檔，不需要自己解壓縮。**

若你已經有可用的 Ubuntu 18.04 rootfs，可直接使用既有檔案，不必重複下載。

請勿改用 Ubuntu 22.04／24.04 rootfs，因為後續安裝的 ROS Melodic 是針對 Ubuntu 18.04 的環境。

#### 方式 A：使用 CMD 安裝精靈（推薦）

1. 在 Windows 瀏覽器打開 **[`setup_wsl_ubuntu1804.cmd`](scripts/setup_wsl_ubuntu1804.cmd)**。

2. 在 GitHub 檔案頁面按 **Download raw file**，將檔案儲存在 Windows 的 **「下載」資料夾**。

   確認檔名是 `setup_wsl_ubuntu1804.cmd`，**不是 `.cmd.txt`**。

3. 建議先用記事本檢視檔案內容，確認來源是本專案。

   精靈只有**一個 `.cmd` 檔案**，不需要另外下載 `.ps1`。

4. 在檔案總管**雙擊 `setup_wsl_ubuntu1804.cmd`**。

   也可以開啟一般權限的 **Windows CMD（命令提示字元）**，輸入：

```bat
"%USERPROFILE%\Downloads\setup_wsl_ubuntu1804.cmd"
```

這一行是 **Windows CMD 指令**，不是在 Ubuntu WSL 終端機裡執行。

如果 `.cmd` 存在別的位置，請改成實際路徑。**不需要以系統管理員身分開啟精靈**；若 WSL2 尚未啟用，請先回到 1.1 完成 Windows 安裝。

**開啟成功時**，你會看到 `Autoware-Lite | Ubuntu 18.04 WSL2 匯入精靈`，接著看到 `[環境檢查]` 與 `[成功] 已找到 WSL 指令。`。

- 若出現「找不到 wsl.exe」，請先依 1.1 安裝 WSL2。

- 若全新電腦顯示「尚未偵測到已匯入的發行版」，則是正常的。

精靈會詢問以下三項設定。**沒有特殊需求時，建議直接按 Enter 使用預設值。**

**① WSL2 安裝資料夾**

- 預設：`%USERPROFILE%\WSL\Autoware1804`
- 建議：沒有指定磁碟需求就按 **Enter**；也可自行輸入 `D:\WSL\Autoware1804`。

**② WSL 發行版名稱**

- 預設：`Autoware-18.04`
- 建議：**直接按 Enter**，後續 README 的指令就不用修改名稱。

**③ Ubuntu rootfs 檔案**

- 預設：`%USERPROFILE%\Downloads\ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz`
- 建議：檔案在預設位置且沒改名就按 **Enter**；否則貼上實際完整路徑。

> [!TIP]
> `%USERPROFILE%` 代表 Windows 的個人資料夾，例如 `C:\Users\Cobe`，**不用自己修改 Windows 使用者名稱**。
>
> 如果 rootfs 放在其他位置，可以在 Windows 11 檔案總管對檔案按**滑鼠右鍵 →「複製路徑」**，再直接貼進精靈。
>
> 例如：`"D:\課程資料\Ubuntu 18.04\ubuntu-18.04.rootfs.tar.gz"`
>
> **不用自行刪除外層雙引號**，精靈會處理。

三項輸入通過檢查後，會依序看到類似訊息：

```text
[成功] 安裝資料夾可使用：D:\WSL\Autoware1804
[成功] 發行版名稱可使用：Autoware-18.04
[成功] 已找到 rootfs 檔案：D:\課程資料\Ubuntu 18.04\ubuntu-18.04.rootfs.tar.gz
```

這些路徑只是範例，實際會顯示你的設定。

**若畫面出現黃色「提醒」，請依提示重新輸入，直到看到「成功」再繼續。**

名稱已存在、資料夾非空白時，請確認原本環境的用途，**不要為了重試而刪除資料**。

精靈最後會顯示安裝摘要。請先確認名稱、安裝資料夾及 rootfs 都正確。

- 輸入 **`Y`** 並按 Enter：開始匯入。

- **直接按 Enter** 或輸入 **`N`**：取消匯入。

匯入可能需要數分鐘，**請勿關閉視窗**。

**匯入成功時**應看到類似：

```text
[成功] 已匯入 WSL2 發行版：Autoware-18.04
NAME             STATE           VERSION
Autoware-18.04   Running         2
[成功] Ubuntu 版本為 18.04，可以繼續 README 第 1.3 節。
```

`STATE` 也可能顯示 `Stopped`，不影響已匯入的判斷。

**重點是發行版名稱正確、`VERSION` 為 `2`，Ubuntu 版本為 18.04。**

若顯示「已匯入，但無法自動確認 Ubuntu 版本」，請在 Windows CMD 執行：

```bat
wsl -d Autoware-18.04 -- cat /etc/os-release
```

確認出現 `VERSION_ID="18.04"` 後再繼續。

最後精靈會詢問是否立即開啟 Ubuntu：

- 要開啟請輸入 **`Y`**。
- **直接按 Enter** 表示先不開啟。

日後隨時可在 Windows CMD 輸入 `wsl -d Autoware-18.04` 開啟。

> [!IMPORTANT]
> 本精靈**不會執行 `wsl --unregister`、刪除既有發行版或覆寫非空資料夾**。
>
> 如果匯入失敗，畫面會保留錯誤與診斷方向，且不會自動清理資料。
>
> 它**只建立 Ubuntu 18.04 WSL2**，不會安裝 ROS／Autoware，也不會建立 Linux 一般使用者。
>
> **方式 A 成功後直接前往 [1.3](#13-建立-linux-使用者)，不要再執行方式 B。**

#### 方式 B：PowerShell 手動匯入（僅供未使用方式 A 者選用）

**只有尚未使用方式 A 成功匯入 Ubuntu 18.04，才需要以下指令。**

若已完成方式 A，請跳過整個方式 B，直接前往 1.3。

以下是在 Windows **PowerShell** 執行的手動做法，**不是 CMD 或 Ubuntu 終端機**。不熟悉指令的使用者建議選方式 A。

> [!WARNING]
> **`<WindowsUser>` 代表電腦上的「Windows 使用者資料夾名稱」。**
>
> 也就是 `C:\Users\` 後面的那一段，**不是 GitHub 帳號，也不是稍後建立的 Linux 使用者名稱**。
>
> 例如資料夾是 `C:\Users\Cobe`，那麼 `<WindowsUser>` 就是 `Cobe`。
>
> 可以在 **Windows PowerShell** 輸入 `$env:USERPROFILE`，查看自己的實際資料夾路徑。

以下使用 PowerShell 的 **`$env:USERPROFILE` 自動取得 Windows 個人資料夾**，不用自行修改 `<WindowsUser>`。

如果希望把 Ubuntu 安裝在其他磁碟，可修改 `$InstallDir`；沒有偏好就保留範例值。

**請在同一個 PowerShell 視窗，按照 ①～④ 的順序執行：**

**① 設定檔案與安裝路徑**

```powershell
$env:USERPROFILE
$UbuntuRootfs = Join-Path $env:USERPROFILE 'Downloads\ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz'
$InstallDir = 'D:\WSL\Autoware1804'
```

**② 檢查 rootfs 與目標資料夾**

```powershell
Test-Path $UbuntuRootfs
if (-not (Test-Path $UbuntuRootfs)) { throw "找不到 Ubuntu rootfs，請先確認 Downloads 位置：$UbuntuRootfs" }

if (Test-Path $InstallDir) {
    if (Get-ChildItem -LiteralPath $InstallDir -Force | Select-Object -First 1) {
        throw "安裝資料夾不是空的，請換一個資料夾：$InstallDir"
    }
}
```

**③ 匯入 Ubuntu 18.04**

```powershell
New-Item -ItemType Directory -Force $InstallDir
wsl --import Autoware-18.04 "$InstallDir" "$UbuntuRootfs" --version 2
if ($LASTEXITCODE -ne 0) { throw 'WSL 匯入失敗，請查看上一行錯誤訊息。' }
```

**④ 確認結果**

```powershell
wsl --list --verbose
wsl -d Autoware-18.04 -- cat /etc/os-release
```

其中 `Test-Path $UbuntuRootfs` 應顯示 `True`。

如果是 `False`，表示下載檔案不在預期的 Downloads 資料夾；請先確認實際位置，再修改 `$UbuntuRootfs`，**不要繼續匯入**。

**手動匯入成功的判斷：**

- `wsl --list --verbose` 列出 `Autoware-18.04`，`VERSION` 為 `2`。

- `cat /etc/os-release` 的輸出包含 `VERSION_ID="18.04"`。

如果同名發行版已存在，`wsl --import` 會拒絕重複建立；請先檢查原有系統，**不要執行 `wsl --unregister`**。

`wsl --import` 不會自動建立一般 Linux 使用者。新匯入環境通常先以 `root` 開啟。

**方式 B 成功匯入後，同樣直接進入 [1.3 建立 Linux 使用者](#13-建立-linux-使用者)，不需要回頭執行方式 A 的安裝精靈。**

### 1.3 建立 Linux 使用者

**這一節開始使用 Ubuntu WSL 終端機，不再是 Windows CMD。**

若剛剛沒有選擇立即開啟 Ubuntu，請在 Windows CMD 執行：

```bat
wsl -d Autoware-18.04
```

在 Ubuntu 輸入以下指令，確認目前登入的使用者與系統版本：

```bash
whoami

cat /etc/os-release
```

首次匯入的 rootfs 通常以 `root` 身分開啟；系統版本應包含 `VERSION_ID="18.04"`。

**如果 `whoami` 已顯示自己的 Linux 一般使用者名稱，可略過建立帳號的指令。**

如果顯示 `root`，請建立一般使用者。Linux 使用者名稱可以與 Windows 帳號不同。

以下以 `autoware` 為範例；若想用自己的帳號名稱，請在本節每個出現 `autoware` 的地方一致替換。

在 **Ubuntu（root 終端機）**依序輸入：

```bash
adduser autoware

usermod -aG sudo autoware
```

`adduser` 會要求輸入兩次 Linux 密碼。輸入密碼時畫面**不會顯示任何字元**，屬於正常現象。

若詢問 Full Name、Room Number 等個人資料，沒有需要就直接按 Enter 跳過，最後確認 `Y`。

完成後輸入 `id autoware`。如果看到 `uid=...`，且群組包含 `sudo`，代表帳號及管理權限設定成功。

接著用終端機文字編輯器設定預設登入帳號，避免每次開啟 Ubuntu 都是 root：

```bash
nano /etc/wsl.conf
```

若系統提示 `nano: command not found`，可以先執行 `apt update`、`apt install -y nano` 後再重試。

在檔案中加入以下內容。**若已有其他設定，請保留既有內容，只新增或修改 `[user]` 區段**：

```ini
[user]
default=autoware
```

在 nano 按 **Ctrl+O → Enter** 儲存，再按 **Ctrl+X** 離開。

關閉 Ubuntu 視窗，改回 **Windows CMD** 執行以下指令，讓預設使用者設定生效：

```bat
wsl --terminate Autoware-18.04

wsl -d Autoware-18.04 --cd ~
```

**成功判斷**：在重新開啟的 Ubuntu 終端機輸入：

```bash
whoami

pwd

cat /etc/os-release | grep VERSION_ID
```

應依序看到：

```text
autoware
/home/autoware
VERSION_ID="18.04"
```

若使用其他 Linux 帳號名稱，前兩項會不同。

**確認這三項正確後，再進入第 2 節安裝 ROS Melodic。**

若當初自訂了 WSL 發行版名稱，Windows 指令中的 `Autoware-18.04` 也必須改成該名稱。

## 2. Ubuntu：安裝 ROS Melodic

以下命令均在 Ubuntu 18.04 WSL 執行，除非明確標示 PowerShell。

### 2.1 設定 ROS apt 套件來源

**① 更新 Ubuntu 套件資訊，安裝下載與金鑰工具**

```bash
sudo apt update
sudo apt install -y curl ca-certificates gnupg2 lsb-release
```

**② 加入 ROS 套件來源與金鑰**

```bash
curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | \
  gpg --dearmor | \
  sudo tee /usr/share/keyrings/ros-archive-keyring.gpg > /dev/null

printf '%s\n' \
  'deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros/ubuntu bionic main' | \
  sudo tee /etc/apt/sources.list.d/ros1-latest.list
```

**③ 重新更新套件資訊，確認 ROS Melodic 可安裝**

```bash
sudo apt update

apt-cache policy ros-melodic-ros-base
```

**成功判斷：**

- 最後一個 `sudo apt update` 沒有 `E:`、`NO_PUBKEY`、`EXPKEYSIG` 或 404 等錯誤。

- `apt-cache policy ros-melodic-ros-base` 能列出 `Candidate:` 版本（不是 `(none)`）。

符合以上條件，就可以繼續 2.2。

若來源失效，先檢查 ROS 封存套件源與金鑰；**不要使用 `trusted=yes` 或關閉簽章驗證強行安裝**。

### 2.2 安裝 Melodic 及建置工具

**① 安裝 ROS Melodic**

```bash
sudo apt install -y ros-melodic-desktop-full
```

**② 讓 Ubuntu 終端機載入 ROS 環境**

```bash
grep -qxF 'source /opt/ros/melodic/setup.bash' ~/.bashrc || printf '\nsource /opt/ros/melodic/setup.bash\n' >> ~/.bashrc

source /opt/ros/melodic/setup.bash
```

**③ 安裝建置工具**

```bash
sudo apt install -y git cmake build-essential python-catkin-pkg python-rosdep \
  ros-melodic-catkin python3-pip python3-setuptools \
  python3-colcon-common-extensions python3-vcstool
```

**④ 確認 ROS 版本**

```bash
rosversion -d
```

**成功判斷：**`sudo apt install` 完成後沒有 `E: Unable to locate package` 或其他安裝失敗訊息，`rosversion -d` 應顯示：

```text
melodic
```

如果提示 `rosversion: command not found`，先確認 ROS 安裝完成，並重新執行 `source /opt/ros/melodic/setup.bash`。

**⑤ 初始化 rosdep（只需執行一次）**

```bash
sudo rosdep init
```

**⑥ 更新 Melodic 的 rosdep 索引**

```bash
rosdep update --include-eol-distros --rosdistro melodic
```

> [!IMPORTANT]
> **ROS Melodic 已停止維護（EOL）。**
>
> 更新 rosdep 時需要加上 `--include-eol-distros`，才能包含 Melodic；`--rosdistro melodic` 表示只更新本教學需要的 ROS 發行版索引。
>
> **成功判斷：**輸出包含 `Add distro "melodic"`，且最後沒有下載錯誤。確認後才能繼續下一節。

若執行 `sudo rosdep init` 出現 `rosdep sources list file already exists`，代表**已初始化，不必重做這一步**。

直接執行：

```bash
rosdep update --include-eol-distros --rosdistro melodic
```

**不要改用未加參數的 `rosdep update`**，否則可能略過已停止維護的 Melodic，造成後續 `Cannot locate rosdep definition` 等依賴解析問題。

第 3.3 節的 `rosdep check` 用途是檢查依賴；若缺少套件，再使用該節的 `rosdep install`。

開啟新的 Ubuntu 終端機後，也可以用 `rosversion -d` 確認仍為 `melodic`。

若要測試 ROS Master，可暫時執行 `roscore`，成功後按 `Ctrl+C` 結束。**啟動 GUI 時不要另外留下重複的 master／localizer 節點。**

### 2.3 檢查圖形介面與中文字体

**① 檢查顯示環境**

```bash
echo "$DISPLAY"
```

**② 安裝 GUI 與中文字型**

```bash
sudo apt install -y python3-pyqt5 fonts-noto-cjk fonts-wqy-microhei fontconfig

fc-cache -fv

fc-match 'Noto Sans CJK TC'
```

**成功判斷：**

- `echo "$DISPLAY"` 輸出非空的顯示位址。

- `fc-match 'Noto Sans CJK TC'` 能找到中文字型。

Windows 11 WSLg 通常可以直接開啟 `rviz`／PyQt5。

若 GUI 無法顯示，先解決 WSLg 或 X Server 問題，**不要直接硬設 `DISPLAY=:0`**。

若 RViz 因顯示卡驅動失敗，可測試 `LIBGL_ALWAYS_SOFTWARE=1 rviz`（可能較慢）。圖形環境正常後再繼續。

## 3. 安裝 Autoware.AI 1.14.0（只編譯需要的套件）

### 3.1 取得本 GitHub repository

在 WSL clone **SeaFu/autoware-lite**：

```bash
git clone https://github.com/SeaFu/autoware-lite.git ~/autoware-lite
```

下載完成後，進入專案並確認檔案存在：

```bash
cd ~/autoware-lite

pwd

ls README.md scripts/setup_wsl_ubuntu1804.cmd
```

**成功判斷：**

- `git clone` 完成時沒有 `fatal:` 錯誤。

- `pwd` 顯示 `/home/你的Linux帳號/autoware-lite`。

- `ls` 能列出 README 與安裝精靈檔案。

若 `git clone` 顯示目標資料夾已存在，先檢查原有資料夾，不要直接刪除。已經有正確的 `~/autoware-lite` 時，直接 `cd ~/autoware-lite` 繼續即可。

### 3.2 還原原始碼版本

此專案只需要 `messages`、`common`、`core_perception`、`utilities`、`core_planning`。

**不要把 GUI 當 catkin package 放進 Autoware `src`。**

**① 建立工作空間並下載對應原始碼**

```bash
mkdir -p ~/autoware.ai/src

vcs import ~/autoware.ai/src < manifests/autoware_minimal.repos
```

**② 查看下載後的原始碼狀態**

```bash
cd ~/autoware.ai

vcs status src
```

這會下載所需的 Autoware-AI 原始碼與 `autoware_ai_planning`（`core_planning`），並固定 `1.14.0` 版本。

**成功判斷：**`vcs import` 沒有 `ERROR` 或 clone 失敗，`vcs status src` 能列出各個來源的狀態。

若你已有能正常運作的 `~/autoware.ai`，**先記錄版本及本地修改**，不要直接在原目錄覆蓋或重跑 `vcs import`。

原版完整清單可參考 [Autoware.AI 1.14 官方 `autoware.ai.repos`](https://github.com/autowarefoundation/autoware_ai/blob/1.14.0/autoware.ai.repos)。

本專案使用較小的教學專用清單，不包括全部感測器、模擬、GNSS 及視覺化模組。

### 3.3 安裝必要相依套件

**① 安裝 Lanelet2，並檢查缺少的相依套件**

```bash
sudo apt install -y ros-melodic-lanelet2

cd ~/autoware.ai

rosdep check \
  --from-paths $(colcon list --packages-up-to lidar_localizer --paths-only) \
  --ignore-src \
  --rosdistro melodic
```

`rosdep check` 用於**檢查**缺少的依賴，不負責安裝。

第一次執行時若列出缺少的套件，不代表前面的 Ubuntu 匯入失敗。

**② 補齊需要的依賴**

確認 ROS apt 套件源可用後，執行：

```bash
sudo apt install -y libgeographic-dev

rosdep install -y \
  --from-paths $(colcon list --packages-up-to lidar_localizer \
    autoware_connector waypoint_maker pure_pursuit twist_filter --paths-only) \
  --ignore-src \
  --rosdistro melodic \
  --skip-keys="geographiclib libgeographiclib-dev"
```

**成功判斷：**`rosdep install` 執行後沒有 `ERROR` 或 `Cannot locate rosdep definition`，就可以繼續編譯。

必要時可重新執行 `rosdep check`。

如果 EOL 套件源找不到特定依賴，請記下缺少的**具體套件名稱**，查核來源，勿無限制重試。

若 `lanelet2_extension` 找不到 `lanelet2_core`，先確認 `ros-melodic-lanelet2` 已安裝，且已執行 `source /opt/ros/melodic/setup.bash`。

### 3.4 選擇性編譯（CPU NDT + 離線導航）

以下三個步驟請在**同一個 Ubuntu 終端機**依序執行。

**① 編譯 LiDAR 定位套件**

```bash
cd ~/autoware.ai

colcon build --packages-up-to lidar_localizer \
  --parallel-workers 2 \
  --cmake-args -DCMAKE_BUILD_TYPE=Release
```

**② 編譯 Waypoint 與離線導航相關套件**

```bash
colcon build --packages-up-to autoware_connector waypoint_maker pure_pursuit twist_filter \
  --parallel-workers 2 \
  --cmake-args -DCMAKE_BUILD_TYPE=Release
```

**③ 載入編譯完成的工作空間**

```bash
source ~/autoware.ai/install/setup.bash
```

**成功判斷：**兩次 `colcon build` 都結束且輸出包含 `Summary: ... packages finished`，**沒有 `packages failed`**，才進入 GUI 步驟。

若有套件失敗，先查看錯誤中的**第一個失敗 package**，不要盲目全量編譯。

`--parallel-workers 2` 適合記憶體較小的 WSL 電腦；不必編譯 `waypoint_planner`、GPU NDT 或整套 Autoware Runtime Manager。

每次開啟新的 Ubuntu 終端機，都需要載入 `~/autoware.ai/install/setup.bash`。

若想自動載入，可使用下方指令將它加入 `~/.bashrc`（會避免加入完全相同的重複行）：

```bash
grep -qxF 'source ~/autoware.ai/install/setup.bash' ~/.bashrc || printf '\nsource ~/autoware.ai/install/setup.bash\n' >> ~/.bashrc
```

確認 ROS 能找到必要套件：

```bash
rospack find lidar_localizer

rospack find waypoint_maker

rospack find pure_pursuit

rospack find twist_filter

rospack find autoware_msgs
```

**成功判斷：**上述五行都應輸出套件所在路徑，例如 `/home/autoware/autoware.ai/install/...`。

**不應出現 `[rospack] Error: package ... not found`**。全部找到後，才能啟動學生版 GUI。

## 4. 執行學生版 GUI

GUI 已放在 repository 的 `Autoware_GUI/`，不需要另行編譯。

**① 載入 ROS 與 Autoware 環境**

```bash
source /opt/ros/melodic/setup.bash

source ~/autoware.ai/install/setup.bash
```

**② 啟動 GUI**

```bash
cd ~/autoware-lite/Autoware_GUI

python3 autoware_student_gui.py
```

**成功判斷：**畫面會開啟 Autoware 學生版 GUI 視窗，沒有 `ModuleNotFoundError`、`ImportError` 或顯示環境錯誤。

這代表 GUI 已能啟動，**不等於所有建圖／定位功能已經測試通過**。功能驗證請接著依第 5 節逐項進行。

GUI 使用 Python 3；`offline_nav_bridge.py` 會由 GUI 用 Python **2** 啟動，以對應 ROS Melodic。

若終端機出現 `ModuleNotFoundError: PyQt5`，請確認已安裝 `python3-pyqt5`，並使用系統 Python 3，而不是其他 Conda／venv 環境。

進入「01 專案設定」，選擇實際資料所在位置，例如：

| GUI 欄位 | 課程範例（依自己的資料夾修改） |
| --- | --- |
| Autoware 工作空間 | `/home/<LinuxUser>/autoware.ai` |
| LiDAR bag | `/mnt/d/VLP16/mapping.bag` |
| PCD 地圖 | `/home/<LinuxUser>/autoware.ai/maps/vlp16_ndt_01.pcd` |
| CSV 目錄 | `/home/<LinuxUser>/autoware.ai/trajectory` |
| Waypoint CSV | `/home/<LinuxUser>/autoware.ai/trajectory/vlp16_waypoints_01_lf.csv` |

本次實驗以 `base_link → velodyne` 的**零外參**做離線功能測試。

這**不是** Hunter 真正的 LiDAR 外參；其他車輛／感測器須使用實際校正結果。

## 5. 端到端離線驗證流程

以下是已在實驗環境跑通的操作順序。

在 GUI 按「開啟 RViz」或「開啟導航 RViz」，即可載入預設 `.rviz`，不需要自行新增每個 display。

各頁按鈕與參數細節請見 [GUI 操作說明](Autoware_GUI/README.md)。

**① NDT 建圖**

- GUI 動作：進入「02 NDT 建圖」→ 啟動建圖 → 播放 Bag → 儲存 PCD。
- 確認結果：`maps/*.pcd` 有內容，RViz 可以看到地圖。

**② NDT 定位**

- GUI 動作：停止 Mapping → 進入「03 NDT 定位」→ 載入 PCD／Matching → 開始錄製 CSV → 播放 Bag。
- 確認結果：`/ndt_pose` 有資料，並產生 `ndt_matching_*.csv`。

**③ Waypoint**

- GUI 動作：進入「05 Waypoint」，從 NDT CSV 產生 Waypoint，或載入已驗證的 CSV。
- 確認結果：CSV 表頭為 `x,y,z,yaw,velocity,change_flag`。

**④ Pure Pursuit 追蹤**

- GUI 動作：啟動 Waypoint、Pure Pursuit + Filter → 載入 Bag → 播放。
- 確認結果：`/offline_nav/twist_raw` 與 `/offline_nav/twist_cmd` 都有資料。

**⑤ 視覺化與停車**

- GUI 動作：在「05 Waypoint」按「開啟導航 RViz」，觀察路徑、目標與轉向，並播放至路線末段。
- 確認結果：`/offline_nav/twist_cmd/twist/linear/x` 由正值降為 `0.0`。

### 5.1 本次實測的 Topic 及資料

| Topic | 型別 | 用途 |
| --- | --- | --- |
| `/based/lane_waypoints_raw` | `autoware_msgs/LaneArray` | `waypoint_loader` 匯入完整 CSV |
| `/offline_nav/waypoint_path` | `nav_msgs/Path` | RViz 固定顯示完整 Waypoint 路線 |
| `/offline_nav/final_waypoints` | `autoware_msgs/Lane` | 橋接器提供 Pure Pursuit 前方區段 |
| `/offline_nav/current_pose` | `geometry_msgs/PoseStamped` | 轉送 NDT 位姿 |
| `/offline_nav/current_velocity` | `geometry_msgs/TwistStamped` | 原始估計速度或 NDT 差分速度 |
| `/offline_nav/twist_raw` | `geometry_msgs/TwistStamped` | Pure Pursuit 原始指令 |
| `/offline_nav/twist_cmd` | `geometry_msgs/TwistStamped` | Twist Filter 後離線指令 |

實測資料從 `mapping.bag` 產生約 237 筆 NDT 軌跡，並整理為 **49 個 Waypoint、路徑約 27.44 m**。

使用 `2 km/h` 的 Waypoint 速度（**0.55556 m/s**）時，追蹤期間角速度會變化；在播放尾段，濾波後的線速度由 `0.55556` 降為 `0.0`。

這表示**離線命令流程與零速指令轉換成功**，並不代表真車行駛或精確終點位置誤差已通過驗證。

以下可在**另一個已 source ROS 的 WSL 終端機**檢查：

```bash
rostopic hz /offline_nav/waypoint_path

rostopic hz /offline_nav/final_waypoints

rostopic echo -n 1 /offline_nav/twist_raw

rostopic echo -n 1 /offline_nav/twist_cmd

rostopic echo /offline_nav/twist_cmd/twist/linear/x
```

`waypoint_path` 是保留最後一筆的完整路線，**不一定持續以固定頻率發布**。

如 `rostopic hz` 看不到連續數值，改用 `rostopic echo -n 1`，並透過 `rostopic info` 確認有 publisher。

`final_waypoints` 在播放時會持續更新（本次約 10 Hz）。

### 5.2 RViz 要看的項目

在 Waypoint 頁按 **「開啟導航 RViz」**，設定檔是 `Autoware_GUI/rviz/navigation.rviz`：

1. `Fixed Frame = map`。

2. `Waypoint Path (full)`：完整預定路線，Topic `/offline_nav/waypoint_path`。

3. `NDT Pose`：定位箭頭，Topic `/ndt_pose`。

4. `Lookahead Target`／`Next Waypoint`／`Lookahead Search Circle`／`Pursuit Trajectory`：Pure Pursuit Marker。

5. 視需要勾選 PCD Map 與 Live Scan，確認點雲配準是否合理。

觀察目標 Marker 是否隨著 NDT Pose 移動，並確認其位於參考路線前方。

**RViz 顯示目標與軌跡，不會代替控制閉迴路測試。**

Autoware 原版的 `next_target_mark` 等 Marker，若出現 `Uninitialized quaternion, assuming identity` 橘色警告，可能是標記四元數 `w=0` 造成的視覺化警告。

如果 Marker 仍在正確位置且 `twist_raw` 正常，不能僅憑這個警告判定追蹤演算法失敗。

## 6. 常見故障與修正

**1. `/waypoint_loader` 看似存在，但 `rosnode info` 連線失敗**

- 可能原因：`waypoint_loader` 已崩潰，只留下 ROS Master 舊註冊。
- 處理方式：用 `pgrep -af waypoint_loader` 確認；必要時以 `rosnode cleanup` 清除無效紀錄，修好 CSV 後重新啟動。

**2. `terminate called ... std::invalid_argument / stoi`**

- 可能原因：Waypoint CSV 的 **CRLF** 行尾使 v3 欄位 `change_flag\r` 辨識失敗。
- 處理方式：先轉換 LF：`sed 's/\r$//' 原始.csv > 修正_lf.csv`，再於 GUI 選擇修正檔。

**3. `Necessary topics are not subscribed yet`／`Pose=0, Waypoint=1, Velocity=0`**

- 可能原因：`/clock`、`/ndt_pose` 或 velocity 尚未收到。
- 處理方式：確認 Bag 已用 `--clock` 播放、NDT Matching 已初始化，且 `/offline_nav/current_pose`、`/offline_nav/current_velocity` 有訊息。

**4. `Waypoint=0`，但其餘資料正常**

- 檢查 `/based/lane_waypoints_raw` 是否真的有路線。
- 確認 bridge 已發布 `/offline_nav/final_waypoints`，並檢查 `rosnode info /offline_pure_pursuit` 的訂閱連線。

**5. `/offline_nav/twist_raw` 全是 `0.0`**

- 檢查 Waypoint CSV 的速度欄、Pure Pursuit `param_flag`（GUI 內設定）。
- 同時確認路徑前方區段及 NDT Pose 是否正確。

**6. `twist_raw` 角速度非 0，但 `twist_cmd` 角速度永遠是 `0.0`**

- 確認 Twist Filter 收到 `/offline_nav/config/twist_filter`。
- 其中必須包含 **`lateral_jerk_limit: 5.0`**；缺少此欄可能使角速度被限制成 0。GUI 已包含這個參數。

**7. `rostopic echo` 顯示 `simulated time is active`**

- 這是 `/use_sim_time=true` 的一般提醒，不代表 `/clock` 一定故障。
- 執行 `rostopic hz /clock`，並確認 Bag 正在播放（而非暫停）。

**8. RViz Marker 出現橘色 `Uninitialized quaternion`**

- 可能是原版 Marker 的 identity quaternion 未初始化。
- 需另外觀察 Pose、Target 與 Twist 是否正常，不能只靠這個視覺化警告判定失敗。

**9. GUI 顯示重複 node 或無法啟動**

- 關閉手動啟動的 `ndt_mapping`、`ndt_matching`、`rosbag play` 及其他同名程序。
- 不要同時使用兩個 ROS Master。

**10. `rospack find` 找不到 package**

- 重新執行 `source /opt/ros/melodic/setup.bash` 與 `source ~/autoware.ai/install/setup.bash`。
- 檢查 colcon 失敗的 package，以及 rosdep 相依套件。

本次 Waypoint 換行修正範例：

```bash
sed 's/\r$//' ~/autoware.ai/trajectory/vlp16_waypoints_01.csv > ~/autoware.ai/trajectory/vlp16_waypoints_01_lf.csv

sed -n '1l' ~/autoware.ai/trajectory/vlp16_waypoints_01_lf.csv
```

修正後表頭應顯示 `x,y,z,yaw,velocity,change_flag$`（沒有 `\r$`）。

## 7. 保留「目前的 autoware.ai」版本和修改

新電腦要精確重建**現在這台 WSL 的 Autoware**，只記錄 tag 並不夠。

任何自行修改的 `.cpp`、`.launch` 或其他本機檔案，都需要另外保存。

可使用下方只讀匯出腳本：

```bash
cd ~/autoware-lite

bash scripts/capture_autoware_state.sh ~/autoware.ai
```

這個腳本會記錄：

- `vcs export --exact`（若本機 vcstool 支援）。

- 各 Git 倉庫的 HEAD、status 及已追蹤檔案的差異。

- 輸出位置：`docs/local-autoware-state/`。

**腳本不會修改 Autoware。**

匯出結果可能包含本機資訊，**提交 GitHub 前請人工檢查私人檔案、路徑、token 或不想公開的修改**。

此腳本不會自動包含 untracked 原始檔，這些請自行審核後加入版本控制。

若沒有任何本機修改，只需保存 `manifests/autoware_minimal.repos`。

如果需要逐 commit 精確鎖版，可審核匯出的 `autoware.local.lock.repos` 後取代原清單。

**不要提交到 GitHub 的資料：**

- `~/autoware.ai/build`、`install`、`log`。
- 大量 `.bag`、`.pcd` 與原始感測資料。
- 含隱私資訊的 CSV。

## 8. GUI 測試與後續規劃

不用 ROS，也能先跑 GUI 核心單元測試：

```bash
cd ~/autoware-lite/Autoware_GUI

python3 -m unittest discover -s tests -v
```

**已驗證的功能：**

- NDT Mapping／Matching GUI、Waypoint CSV。
- 離線 Pure Pursuit 命令、Twist Filter。
- 三組 RViz profile 與停速訊號的人工驗證。

**尚未完成的項目：**

- 精確終點距離／yaw 誤差量化、自動化 bag 回歸測試。
- 真車底盤指令與安全回路。
- 避障與 GNSS／IMU 融合。

## 上游文件

- [Microsoft：匯入 WSL 發行版](https://learn.microsoft.com/windows/wsl/use-custom-distro)
- [Autoware.AI GitHub（已封存）](https://github.com/autowarefoundation/autoware_ai)
- [Autoware.AI 1.14 原始碼版本清單](https://github.com/autowarefoundation/autoware_ai/blob/1.14.0/autoware.ai.repos)
- [Autoware AI Planning / core_planning](https://github.com/autowarefoundation/autoware_ai_planning)
- [Ubuntu 18.04 支援週期](https://ubuntu.com/about/release-cycle)

本 README 根據課程安裝簡報與已驗證的 WSL 操作紀錄整理；版本清單、原始碼與 GUI 為不同來源，請遵守各上游授權條款。
