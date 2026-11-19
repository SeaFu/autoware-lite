# Autoware-Lite: Lightweight Autoware.AI Framework for Mapping and Navigation

**基於 Autoware.AI 1.14.0 的非官方精簡教學專案**，整理 **Windows 11 → WSL2 Ubuntu 18.04 → ROS Melodic → Autoware.AI → PyQt5 GUI** 的可重現流程。最初以 Hunter／VLP-16 錄製資料進行離線驗證：

- **NDT Mapping**：播放 ROS bag、建立與匯出 PCD 地圖。
- **NDT Matching**：使用 PCD 對 bag 點雲定位，記錄 NDT 位姿與統計 CSV。
- **Waypoint**：從定位軌跡產生、檢查及載入 Autoware Waypoint CSV。
- **Pure Pursuit + Twist Filter**：從離線路徑產生速度與角速度命令，在 RViz 檢視目標點、搜尋圓與路徑。

> **重要安全邊界**：本專案只驗證 `/offline_nav/*` 的**離線指令產生**。沒有接 Hunter 車體控制、沒有障礙物避讓／急停，也不等於具備實車自主導航能力。請勿將離線輸出直接接到馬達控制器。

### 文件導覽

- [環境與版本](#0-相容環境與注意事項) → [WSL2 安裝](#1-windows建立-ubuntu-1804-wsl2) → [ROS Melodic](#2-ubuntu安裝-ros-melodic)
- [Autoware.AI 編譯](#3-安裝-autowareai-1140只編譯需要的套件) → [啟動 GUI](#4-執行學生版-gui)
- [離線驗證](#5-端到端離線驗證流程) → [常見問題](#6-常見故障與修正) → [本機版本記錄](#7-保留目前的-autowareai-版本和修改)

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
├── scripts/setup_wsl_ubuntu1804.cmd # Windows CMD：互動式建立 Ubuntu 18.04 WSL2
├── scripts/capture_autoware_state.sh
└── .gitignore
```

**關於 `autoware.ai` 原始碼**：它是 Autoware Foundation 的第三方開源專案，**不是**這個 GUI 的自有程式。本倉庫以 `.repos` 清單記錄來源及版本，不重複上傳完整上游 Autoware 原始碼或編譯產物。若你的 WSL 已修改任何 Autoware C++ 檔案，請先依後面的「記錄本機版本／修改」另存補丁，否則僅從 tag 重建不會包含這些修改。

## 0. 相容環境與注意事項

| 項目 | 版本／用途 |
| --- | --- |
| Windows | Windows 11（CMD／PowerShell + WSL2） |
| Linux | WSL2 Ubuntu **18.04 Bionic**，發行版名稱範例 `Autoware-18.04` |
| ROS | ROS 1 **Melodic**（主要 ROS 節點用 Python 2） |
| Autoware | **Autoware.AI 1.14.0**，選擇性編譯 `lidar_localizer` 與必要導航節點 |
| GUI | Python 3 + `python3-pyqt5`；RViz 需可用的 Linux 圖形介面 |
| 資料 | VLP-16 `sensor_msgs/PointCloud2` ROS bag（範例 `/points_raw`） |

**已停止維護的舊版環境**：Ubuntu 18.04 一般支援已於 2023 年結束、ROS Melodic 已 EOL，Autoware.AI 亦已封存。因套件源、金鑰及依賴可能改變，以下是**本次實驗環境的重建紀錄**，並非保證在任何全新 Windows 電腦可無修改安裝。建議在隔離 WSL／教學主機使用，勿作公開網路服務。

## 1. Windows：建立 Ubuntu 18.04 WSL2

### 1.1 啟用 WSL2（Windows CMD）

先在 Windows 啟用 WSL2（未安裝者可依 [Microsoft WSL 官方說明](https://learn.microsoft.com/windows/wsl/install) 完成，必要時重新開機）。**如果你的電腦已經能正常執行 WSL2，可以略過此節，直接前往 1.2。**

如果要依照本文件操作，請在 Windows 開始功能表搜尋 **`cmd`（命令提示字元）→「以系統管理員身分執行」**，輸入：

```bat
wsl --install --no-distribution
```

這會安裝／啟用 WSL 所需元件，但**不額外安裝預設 Ubuntu 發行版**；下一節會自行匯入指定版本 Ubuntu 18.04。若 Windows 要求重新開機，請先重新開機，**不要在重開機前繼續執行匯入精靈**。

重新開機後，再開啟 Windows CMD（一般權限即可）檢查：

```bat
wsl --update
wsl --set-default-version 2
wsl --status
```

`wsl --status` 用來查看 WSL 設定；**在尚未匯入任何 Linux 發行版的全新電腦上，出現「沒有已安裝的發行版」並不代表 Ubuntu 18.04 匯入失敗**。新的安裝精靈不會把 `wsl --status` 的非零回傳值直接視為無法匯入；是否能使用 WSL2，會以實際執行 `wsl --import ... --version 2` 的結果為準。

如果 `wsl --install --no-distribution` 不支援或啟用失敗，可依 [Microsoft WSL 手動安裝步驟](https://learn.microsoft.com/windows/wsl/install-manual) 在**管理員 CMD** 分別啟用兩個 Windows 元件：

```bat
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

手動啟用後也需要重新開機，再執行 `wsl --update`、`wsl --set-default-version 2`。若仍無法啟用，先檢查 Windows 版本及 BIOS／UEFI 虛擬化功能，依 Microsoft 官方疑難排解處理。**不需同時執行上述兩種安裝方法。**

### 1.2 匯入 Ubuntu 18.04 rootfs（推薦使用 CMD 精靈）

下載課程簡報採用的 [Ubuntu 18.04 WSL rootfs](https://cloud-images.ubuntu.com/releases/bionic/release/ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz)，放在 Windows `Downloads`。若檔案已移到封存或網址失效，請使用可信任的 Ubuntu 18.04 原始映像，勿任意改成 Ubuntu 22.04／24.04（與 Melodic 不相容）。

下載本專案的 **[`setup_wsl_ubuntu1804.cmd`](scripts/setup_wsl_ubuntu1804.cmd)**（進入 GitHub 檔案頁面後按 **Download raw file**），儲存在 Windows 的 `Downloads`，確認副檔名為 `.cmd`（不要存成 `.txt`）。先用記事本查看內容，確認是本 Repository 提供的腳本。之後可在檔案總管**雙擊**，也可以開啟一般權限的 **Windows CMD（命令提示字元）**，貼上以下指令執行：

```bat
"%USERPROFILE%\Downloads\setup_wsl_ubuntu1804.cmd"
```

這一行是 **Windows CMD 指令**，不是在 Ubuntu WSL 終端機裡執行。如果 `.cmd` 存在別的位置，請改成實際路徑；檔案路徑中有空白時，保留左右雙引號。

安裝精靈會依序詢問：

| 步驟 | 輸入項目 | 預設值／範例 |
| --- | --- | --- |
| 1 | **WSL2 安裝資料夾** | `%USERPROFILE%\WSL\Autoware1804`（也能自行指定 `D:\WSL\Autoware1804`） |
| 2 | **WSL 發行版名稱** | `Autoware-18.04`（直接按 Enter） |
| 3 | **Ubuntu rootfs 檔案** | `%USERPROFILE%\Downloads\ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz` |

輸入完成後會顯示摘要，**確認 `Y` 才會執行 `wsl --import ... --version 2`**。即使 `wsl --list --verbose` 顯示「尚未安裝任何 Linux 發行版」，也屬於首次匯入前的正常狀態，不需要先從 Microsoft Store 另外安裝 Ubuntu。

如果 rootfs 不存在、安裝資料夾已有檔案或匯入失敗，精靈會停止並報錯；**不會執行 `wsl --unregister`、清除既有發行版或覆寫非空資料夾**。匯入完成後可選擇立即開啟 Ubuntu。

> [!TIP]
> 確認 Windows 已有 WSL2、也已下載 Ubuntu 18.04 rootfs。

> [!IMPORTANT]
> 這個 `.cmd` **只負責建立 Ubuntu 18.04 的 WSL2 發行版**，不會自行建立 Linux 一般使用者或安裝 ROS／Autoware。成功匯入後，請繼續 **1.3 建立 Linux 使用者**及後面的 ROS 安裝章節。

#### 手動匯入方式（選用：供除錯與教學參考）

若不使用精靈，也能在 Windows **PowerShell** 手動執行。下面保留課程簡報原本的匯入步驟，並加入檔案存在性檢查。

> [!WARNING]
> 🟨 **請特別注意：`<WindowsUser>` 代表你電腦上的「Windows 使用者資料夾名稱」**，也就是 `C:\Users\` 後面的那一段，**不是 GitHub 帳號，也不是稍後建立的 Linux 使用者名稱**。
>
> 例如你的 Windows 使用者資料夾是 `C:\Users\Cobe`，那麼 `<WindowsUser>` 就是 `Cobe`。請先在 **Windows PowerShell** 輸入 `$env:USERPROFILE`，以實際顯示的資料夾路徑為準。

為了避免輸錯使用者名稱，以下使用 PowerShell 的 **`$env:USERPROFILE` 自動取得 Windows 個人資料夾**，因此可整段複製，不需要手動修改 `<WindowsUser>`：

```powershell
$env:USERPROFILE
$UbuntuRootfs = Join-Path $env:USERPROFILE 'Downloads\ubuntu-18.04-server-cloudimg-amd64-wsl.rootfs.tar.gz'
Test-Path $UbuntuRootfs
if (-not (Test-Path $UbuntuRootfs)) { throw "找不到 Ubuntu rootfs，請先確認 Downloads 位置：$UbuntuRootfs" }

New-Item -ItemType Directory -Force D:\WSL\Autoware1804
wsl --import Autoware-18.04 "D:\WSL\Autoware1804" "$UbuntuRootfs" --version 2
wsl --list --verbose
wsl -d Autoware-18.04
```

其中 `Test-Path $UbuntuRootfs` 應顯示 `True`。如果是 `False`，表示下載檔案不在預期的 Downloads 資料夾；請先確認實際存放位置，再修改 `$UbuntuRootfs`，不要繼續匯入。

`wsl --import` 不會自動建立一般 Linux 使用者。新匯入環境通常先以 `root` 開啟。

### 1.3 建立 Linux 使用者

在 **Ubuntu WSL 終端機**中建立自己的 Linux 帳號。**Linux 帳號可以與 Windows 使用者名稱不同**。以下以 `cobe` 為範例，如果想使用別的帳號，請將三處 `cobe` 改成你選定的英文帳號名稱：

```bash
adduser cobe
usermod -aG sudo cobe
apt install gedit
gedit /etc/wsl.conf
```

寫入以下內容（若檔案已有其他 WSL 設定，請保留原有段落）：

```ini
[user]
default=cobe
```

退出 Linux 終端機，再從 **Windows CMD 或 PowerShell** 執行（如果精靈建立時使用其他 WSL 名稱，請替換下方 `Autoware-18.04`）：

```powershell
wsl --terminate Autoware-18.04
wsl -d Autoware-18.04 --cd ~
```

確認 `whoami` 已是剛建立的 Linux 帳號、`pwd` 位於對應的 `/home/帳號名稱`，`cat /etc/os-release` 顯示 Ubuntu 18.04。

## 2. Ubuntu：安裝 ROS Melodic

以下命令均在 Ubuntu 18.04 WSL 執行，除非明確標示 PowerShell。

### 2.1 設定 ROS apt 套件來源

```bash
sudo apt update
sudo apt install -y curl ca-certificates gnupg2 lsb-release
curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | gpg --dearmor | sudo tee /usr/share/keyrings/ros-archive-keyring.gpg > /dev/null
printf '%s\n' 'deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros/ubuntu bionic main' | sudo tee /etc/apt/sources.list.d/ros1-latest.list
sudo apt update
apt-cache policy ros-melodic-ros-base
```

這裡**修正了簡報中的金鑰保存方式**：以 `gpg --dearmor` 轉成 binary keyring，並讓 apt source 使用 `signed-by`。若 `apt update` 出現 `NO_PUBKEY`、`EXPKEYSIG` 或 404，先查核 ROS 封存套件源與金鑰的現況；不要使用 `trusted=yes` 或關閉簽章驗證強行安裝。

### 2.2 安裝 Melodic 及建置工具

```bash
sudo apt install -y ros-melodic-desktop-full
grep -qxF 'source /opt/ros/melodic/setup.bash' ~/.bashrc || printf '\nsource /opt/ros/melodic/setup.bash\n' >> ~/.bashrc
source /opt/ros/melodic/setup.bash

sudo apt install -y git cmake build-essential python-catkin-pkg python-rosdep \
  ros-melodic-catkin python3-pip python3-setuptools \
  python3-colcon-common-extensions python3-vcstool
```

第一次使用 `rosdep`：

```bash
sudo rosdep init
rosdep update
```

若看到 `rosdep sources list file already exists`，表示之前初始化過，無須重複 `sudo rosdep init`；只要執行 `rosdep update`。

在新終端機用 `rosversion -d` 確認為 `melodic`。若要測試 ROS Master，可暫時執行 `roscore`，成功後 `Ctrl+C` 結束（**啟動 GUI 時不要另外留下重複的 master／localizer 節點**）。

### 2.3 檢查圖形介面與中文字体

```bash
echo "$DISPLAY"
sudo apt install -y python3-pyqt5 fonts-noto-cjk fonts-wqy-microhei fontconfig
fc-cache -fv
fc-match 'Noto Sans CJK TC'
```

`$DISPLAY` 不應為空。Windows 11 WSLg 通常可以直接開啟 `rviz`／PyQt5；若無法顯示，先解決 WSLg 或 X Server 問題，**不要直接硬設 `DISPLAY=:0`**。若 RViz 因顯示卡驅動失敗，可先在同一終端機測試 `LIBGL_ALWAYS_SOFTWARE=1 rviz`（可能較慢）。

## 3. 安裝 Autoware.AI 1.14.0（只編譯需要的套件）

### 3.1 取得本 GitHub repository

在 WSL clone **SeaFu/autoware-lite**：

```bash
git clone https://github.com/SeaFu/autoware-lite.git ~/autoware-lite
cd ~/autoware-lite
```

### 3.2 還原原始碼版本

此專案只需要 `messages`、`common`、`core_perception`、`utilities`、`core_planning`。**不要把 GUI 當 catkin package 放進 Autoware `src`**。

```bash
mkdir -p ~/autoware.ai/src
vcs import ~/autoware.ai/src < manifests/autoware_minimal.repos
cd ~/autoware.ai
vcs status src
```

這相當於簡報分別 clone Autoware-AI `messages`／`common`／`core_perception`／`utilities`，再 clone `autoware_ai_planning` 到 `core_planning`，且都固定 `1.14.0` tag。若你已有能正常運作的 `~/autoware.ai`，**先記錄版本及本地修改**，不要直接在原目錄覆蓋或重跑 `vcs import`。

原版完整工作空間清單可參考 [Autoware.AI 1.14 官方 `autoware.ai.repos`](https://github.com/autowarefoundation/autoware_ai/blob/1.14.0/autoware.ai.repos)；本專案用的是較小的教學專用清單，不包括全部感測器、模擬、GNSS 及視覺化模組。

### 3.3 安裝必要相依套件

```bash
sudo apt install -y ros-melodic-lanelet2
cd ~/autoware.ai
rosdep check --from-paths $(colcon list --packages-up-to lidar_localizer --paths-only) --ignore-src --rosdistro melodic
```

`rosdep check` 用於列出缺少的依賴；如已確認 apt source 可用，可讓 rosdep 安裝這次所需套件的依賴：

```bash
rosdep install -y --from-paths $(colcon list --packages-up-to lidar_localizer autoware_connector waypoint_maker pure_pursuit twist_filter --paths-only) --ignore-src --rosdistro melodic
```

若它在 EOL 套件源找不到特定依賴，請記下缺少的**具體套件名稱**，查核 ROS Melodic 封存套件來源，勿無限制重試。若出現 `lanelet2_extension` 找不到 `lanelet2_core`，先確認 `ros-melodic-lanelet2` 已安裝且成功 `source /opt/ros/melodic/setup.bash`。

### 3.4 選擇性編譯（CPU NDT + 離線導航）

```bash
cd ~/autoware.ai
colcon build --packages-up-to lidar_localizer --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release
colcon build --packages-up-to autoware_connector waypoint_maker pure_pursuit twist_filter --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release
source ~/autoware.ai/install/setup.bash
```

若記憶體充裕可以提高 `--parallel-workers`，WSL 記憶體不足時則保持 2。若有套件相依缺失，請先看 `colcon` 錯誤中的**第一個失敗 package**，不要盲目全量編譯。沒有必要在本階段編譯 `waypoint_planner`、GPU NDT 或整套 Autoware Runtime Manager。

每次開新 shell 需要 `source ~/autoware.ai/install/setup.bash`。若想自動載入，確認只有一行後加入 `~/.bashrc`：

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

## 4. 執行學生版 GUI

此 GUI 已放在 repository 的 `Autoware_GUI/`，可直接使用，不需要編譯：

```bash
source /opt/ros/melodic/setup.bash
source ~/autoware.ai/install/setup.bash
cd ~/autoware-lite/Autoware_GUI
python3 autoware_student_gui.py
```

GUI 用 Python 3；`offline_nav_bridge.py` 會由 GUI 用 Python **2** 啟動，以對應 ROS Melodic。若終端機出現 `ModuleNotFoundError: PyQt5`，請確認 `sudo apt install python3-pyqt5`，並用系統 Python 3 而非其他 Conda／venv 執行。

進入「01 專案設定」，選擇實際資料所在位置，例如：

| GUI 欄位 | 課程範例（依自己的資料夾修改） |
| --- | --- |
| Autoware 工作空間 | `/home/<LinuxUser>/autoware.ai` |
| LiDAR bag | `/mnt/d/VLP16/mapping.bag` |
| PCD 地圖 | `/home/<LinuxUser>/autoware.ai/maps/vlp16_ndt_01.pcd` |
| CSV 目錄 | `/home/<LinuxUser>/autoware.ai/trajectory` |
| Waypoint CSV | `/home/<LinuxUser>/autoware.ai/trajectory/vlp16_waypoints_01_lf.csv` |

本次實驗以 `base_link → velodyne` 的**零外參**做離線功能測試；它不是 Hunter 真正的 LiDAR 外參。其他車輛／感測器須使用實際校正結果。

## 5. 端到端離線驗證流程

以下是已在本次實驗環境跑通的操作順序。可在 GUI 按「開啟 RViz」或「開啟導航 RViz」直接載入預設 `.rviz`，不需自行一個個新增 display。每頁按鈕與參數細節請見 [GUI 操作說明](Autoware_GUI/README.md)。

| 階段 | GUI 動作 | 確認結果 |
| --- | --- | --- |
| ① 建圖 | 02 NDT 建圖 → 啟動建圖 → Bag 播放 → 儲存 PCD | `maps/*.pcd` 有內容，RViz 可看到地圖 |
| ② 定位 | 停止 Mapping → 03 NDT 定位 → 載入 PCD／Matching → 先開始錄 CSV → Bag 播放 | `/ndt_pose` 及整理後 `ndt_matching_*.csv` |
| ③ Waypoint | 05 Waypoint → 由 NDT CSV 產生 Waypoint 或載入已驗證 CSV | CSV 表頭為 `x,y,z,yaw,velocity,change_flag` |
| ④ 追蹤 | 啟動 Waypoint、Pure Pursuit + Filter → 載入 Bag → 播放 | `/offline_nav/twist_raw` 和 `/offline_nav/twist_cmd` 有資料 |
| ⑤ 視覺化／停車 | 05 →「開啟導航 RViz」→ 看 Path／目標／轉向，播放至路線末段 | `/offline_nav/twist_cmd/twist/linear/x` 由正值轉為 `0.0` |

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

實測資料：`mapping.bag` → 約 237 筆 NDT 軌跡 → **49 個 Waypoint、路徑約 27.44 m**。使用 `2 km/h` 的 Waypoint 速度（換算為 **0.55556 m/s**），追蹤期間角速度會變化；在本次播放尾段，濾波後的線速度由 `0.55556` 降為 `0.0`。這代表**離線命令流程與零速指令轉換成功**，並非真車行駛或精確終點位置誤差已通過驗證。

以下可在**另一個已 source ROS 的 WSL 終端機**檢查：

```bash
rostopic hz /offline_nav/waypoint_path
rostopic hz /offline_nav/final_waypoints
rostopic echo -n 1 /offline_nav/twist_raw
rostopic echo -n 1 /offline_nav/twist_cmd
rostopic echo /offline_nav/twist_cmd/twist/linear/x
```

`waypoint_path` 是保留最後一筆的完整路線，**不一定持續以固定頻率發布**；如 `rostopic hz` 看不到連續數值，改用 `rostopic echo -n 1` 並確認 `rostopic info` 有 publisher。`final_waypoints` 在播放時持續更新（本次約 10 Hz）。

### 5.2 RViz 要看的項目

在 Waypoint 頁按 **「開啟導航 RViz」**，設定檔是 `Autoware_GUI/rviz/navigation.rviz`：

1. `Fixed Frame = map`。
2. `Waypoint Path (full)`：完整預定路線，Topic `/offline_nav/waypoint_path`。
3. `NDT Pose`：定位箭頭，Topic `/ndt_pose`。
4. `Lookahead Target`／`Next Waypoint`／`Lookahead Search Circle`／`Pursuit Trajectory`：Pure Pursuit Marker。
5. 視需要勾選 PCD Map 與 Live Scan，確認點雲配準是否合理。

觀察目標 Marker 隨著 NDT Pose 移動，並確認其位於參考路線的前方。**RViz 顯示目標與軌跡，不會代替控制閉迴路測試**。Autoware 原版的 `next_target_mark` 等 Marker 若出現 `Uninitialized quaternion, assuming identity` 橘色警告，多半是標記四元數 `w=0` 造成的視覺化警告；若 Marker 仍在正確位置且 `twist_raw` 正常，不能僅憑這個警告判定追蹤演算法失敗。

## 6. 常見故障與修正

| 現象 | 可能原因／處置 |
| --- | --- |
| `/waypoint_loader` 看似存在，但 `rosnode info` 連線失敗 | `waypoint_loader` 已崩潰，只留下 ROS Master 舊註冊。用 `pgrep -af waypoint_loader` 確認；需要時 `rosnode cleanup` 清除無效紀錄，再修好 CSV 重新啟動。 |
| `terminate called ... std::invalid_argument / stoi` | Waypoint CSV **CRLF** 行尾會讓 v3 欄位 `change_flag\r` 辨識失敗；先轉 LF：`sed 's/\r$//' 原始.csv > 修正_lf.csv`，GUI 選修正檔。 |
| `Necessary topics are not subscribed yet`／`Pose=0, Waypoint=1, Velocity=0` | `/clock`、`/ndt_pose` 或 velocity 尚未收到。確認 Bag 已用 `--clock` 播放、NDT Matching 初始化完成、`/offline_nav/current_pose` 及 `/offline_nav/current_velocity` 有訊息。 |
| `Waypoint=0` 且其餘資料正常 | 檢查 `/based/lane_waypoints_raw` 是否真的有路線；以及 bridge 是否正常發布 `/offline_nav/final_waypoints`，確認 `rosnode info /offline_pure_pursuit` 的訂閱連線。 |
| `/offline_nav/twist_raw` 全是 `0.0` | 檢查 Waypoint CSV 的速度欄、Pure Pursuit `param_flag`（GUI 內設定）、路徑前方區段及 NDT Pose 是否正確。|
| `twist_raw` 角速度非 0，但 `twist_cmd` 角速度永遠是 `0.0` | 先確認 Twist Filter 收到 `/offline_nav/config/twist_filter`，**其中必須包含 `lateral_jerk_limit: 5.0`**；省略此欄在本版測試中曾使角速度被限制成 0。GUI 已補上此參數。|
| `rostopic echo` 說 `simulated time is active` | 這是 `/use_sim_time=true` 的一般提醒，不足以證明 `/clock` 故障。用 `rostopic hz /clock`，並確認 Bag 是否正在播放（不是 pause）。 |
| RViz Marker 橘色 `Uninitialized quaternion` | 原版 Marker 的 identity quaternion 未初始化；本次觀察屬視覺化警告，需另看 Pose／Target／Twist 是否正常。 |
| GUI 顯示重複 node 或無法啟動 | 關閉手動啟動的 `ndt_mapping`、`ndt_matching`、`rosbag play` 與其他同名程序；不要同時使用兩個 ROS Master。 |
| `rospack find` 找不到 package | 再次 `source /opt/ros/melodic/setup.bash`、`source ~/autoware.ai/install/setup.bash`，檢查 colcon 失敗 package 和 `rosdep`。 |

本次 Waypoint 換行修正範例：

```bash
sed 's/\r$//' ~/autoware.ai/trajectory/vlp16_waypoints_01.csv > ~/autoware.ai/trajectory/vlp16_waypoints_01_lf.csv
sed -n '1l' ~/autoware.ai/trajectory/vlp16_waypoints_01_lf.csv
```

修正後表頭應顯示 `x,y,z,yaw,velocity,change_flag$`（沒有 `\r$`）。

## 7. 保留「目前的 autoware.ai」版本和修改

新電腦要精確重建**現在這台 WSL 的 Autoware**，只記 tag 不夠；任何自己改過的 `.cpp`、`.launch` 或其他本機修改都必須另行保存。提供只讀匯出腳本：

```bash
cd ~/autoware-lite
bash scripts/capture_autoware_state.sh ~/autoware.ai
```

它會把 `vcs export --exact`（如本機 vcstool 支援）、各個 Git 倉庫的 HEAD、status、追蹤檔差異存到 `docs/local-autoware-state/`，**不會改動 Autoware**。匯出包含本機資訊，**提交 GitHub 前請人工檢查是否有私人檔案、路徑、token 或不想公開的修改**。此腳本不會自動包含 untracked 原始檔，這些請自己審核後加入版本控制。

若沒有任何本機修改，只需保存這份 `manifests/autoware_minimal.repos`；如果需要逐 commit 精確鎖版，可審核匯出的 `autoware.local.lock.repos` 後取代原清單。**不要 commit** `~/autoware.ai/build`、`install`、`log`，以及大量的 `.bag`、`.pcd`、原始感測資料或含隱私資訊的 CSV。

## 8. GUI 測試與後續規劃

不用 ROS，也能先跑 GUI 核心單元測試：

```bash
cd ~/autoware-lite/Autoware_GUI
python3 -m unittest discover -s tests -v
```

已完成：NDT Mapping／Matching GUI、Waypoint CSV、離線 Pure Pursuit 命令、Twist Filter、三組 RViz profile 及停速訊號的人工驗證。尚未完成：精確終點距離／yaw 誤差的量化、自動化 bag 回歸測試、真車底盤指令與安全回路、避障與 GNSS／IMU 融合。

## 上游文件

- [Microsoft：匯入 WSL 發行版](https://learn.microsoft.com/windows/wsl/use-custom-distro)
- [Autoware.AI GitHub（已封存）](https://github.com/autowarefoundation/autoware_ai)
- [Autoware.AI 1.14 原始碼版本清單](https://github.com/autowarefoundation/autoware_ai/blob/1.14.0/autoware.ai.repos)
- [Autoware AI Planning / core_planning](https://github.com/autowarefoundation/autoware_ai_planning)
- [Ubuntu 18.04 支援週期](https://ubuntu.com/about/release-cycle)

本 README 根據課程安裝簡報與已驗證的 WSL 操作紀錄整理；版本清單、原始碼與 GUI 為不同來源，請遵守各上游授權條款。
