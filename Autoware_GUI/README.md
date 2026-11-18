# Hunter / Autoware.AI 學生操作面板（Phase 2：離線導航測試）

這是一個以 **Autoware.AI 1.14、ROS1 Melodic、Ubuntu 18.04 WSL2** 為目標的離線教學 GUI，使用 PyQt5 實作。它會呼叫你已測試成功的原始 Autoware ROS 節點，**沒有改寫 NDT 演算法、沒有重新編譯 Autoware 的需求**。

目前整合：

| 功能 | 說明 |
|---|---|
| NDT Mapping | 啟動 CPU 版 `ndt_mapping`，以 `/points_raw` 建圖 |
| Bag 播放器 | 載入、播放、暫停、停止，支援 0.1–2.0 倍速及 `--clock` |
| PCD 匯出 | 發布 `/config/ndt_mapping_output`，儲存點雲地圖 |
| NDT Matching | 載入 PCD 至 `/points_map`，啟動 `ndt_matching`，可重設地圖原點為初始位姿 |
| 資料記錄 | 記錄 `/ndt_pose`、`/ndt_stat`；建圖時可記錄 `/current_pose` |
| CSV 整理 | 自動把 Pose 四元數換算成 XYZ、Roll/Pitch/Yaw、Yaw（度） |
| RViz | 配備 Mapping / Matching / Navigation 三組檢視設定；Waypoint 頁有「開啟導航 RViz」按鈕 |
| 操作紀錄 | Bag 時間與進度在下方固定一行動態更新，NDT 建圖每 50 筆記錄一次；可勾選「顯示詳細日誌」 |
| 開啟輸出資料夾 | WSL2 優先使用 Windows 檔案總管；一般 Linux 桌面則嘗試 `xdg-open` |
| Waypoint CSV | 將 NDT Matching 軌跡轉為 Autoware.AI v3 格式、檢查跳點／速度，並可載入已有的 Waypoint CSV |
| 離線 Pure Pursuit | `waypoint_loader` → `offline_nav_bridge` → Pure Pursuit → Twist Filter；僅輸出 `/offline_nav/*`，不接車輛控制 |

> **適用範圍**：這一版針對先前以 Hunter + VLP-16 錄製、`/points_raw` 為 `sensor_msgs/PointCloud2` 的**離線 bag**。已新增固定 Waypoint 載入與 Pure Pursuit **命令生成測試**；尚未實現動態避障、自動停障、Hunter 馬達控制、GNSS／IMU 融合或任何實車導航安全機制。

## 一、系統需求

以下為你目前已安裝且通過測試的環境：

- Windows 11 + WSL2 `Autoware-18.04`。
- Ubuntu 18.04 + ROS Melodic。
- `~/autoware.ai/install/setup.bash` 存在，且已完成 `lidar_localizer`、`autoware_msgs` 等相依套件的 `colcon build`。
- Phase 2 另外需要已完成 `waypoint_maker`、`pure_pursuit`、`twist_filter` 和相依的 `autoware_config_msgs` 編譯，可用 `source ~/autoware.ai/install/setup.bash` 後的 `rospack find` 檢查。**本版不要求先編譯 waypoint_planner**，用離線橋接程式代替完整規劃器的 `/final_waypoints` 輸出。
- ROS bag：`/mnt/d/VLP16/mapping.bag`，topic `/points_raw`、frame `velodyne`（本次實測範例）。
- GUI 唯一額外套件：`python3-pyqt5`。採用 Python 3 啟動 GUI，ROS 命令透過獨立 shell 執行，不會把 ROS Melodic 的 Python 2 套件強迫匯入 Python 3。

請在 Windows CMD 開啟你現有的 WSL：

```bat
wsl -d Autoware-18.04
```

在 WSL 安裝 GUI 套件：

```bash
sudo apt update
sudo apt install -y python3-pyqt5
```

把整個 `Autoware_GUI` 資料夾解壓縮到 `/home/cobe/`（也可以放在其他路徑）。若已在使用先前版本，**先關閉 GUI 並備份 `~/Autoware_GUI`**，再把新版檔案複製進去；不需移動到 `autoware.ai/src`。

若你在 Windows 將壓縮檔下載至 `D:\Downloads\Autoware_GUI_Phase2.zip`，可於 WSL 執行：

```bash
cd /home/cobe
unzip /mnt/d/Downloads/Autoware_GUI_Phase2.zip
cd /home/cobe/Autoware_GUI
python3 autoware_student_gui.py
```

如果 `unzip` 尚未安裝：`sudo apt install -y unzip`。

**注意**：這個 GUI 單獨放在 `~/Autoware_GUI/`，或直接留在 GitHub repository 的 `Autoware_GUI/` 執行。**無需加入 Autoware 的 `src`，也不需重跑 `colcon build`**。如果 NDT GUI 舊檔案已有自訂修改，請逐檔比對後合併，避免直接覆蓋。完整從零安裝步驟請見[專案根目錄 README](../README.md)。

## 二、使用前檢查

### 介面文字大小

- GUI 目前預設以 **17 px** 顯示主要文字（原版 13 px），ROS 日誌也從原版 11 px 放大為 **15 px**；視窗預設尺寸為 1280 × 900。
- 視窗右上角新增「**介面字級**」調整框，可選 **14–22 px**。選擇 19 或 20 px 可進一步放大字體，無需改程式。
- 字級改動會同步作用於頁籤、標籤、按鈕、輸入框、提示及日誌，並自動儲存；工作頁面支援捲動，因此放大字體後可往下查看控制項。
- 這項調整只影響介面排版，**不會更改 NDT 參數或 ROS 節點設定**。

1. 停止先前手動執行的 `ndt_mapping`、`ndt_matching`、`rosbag play`、靜態 TF 及地圖發布程序，避免同名 ROS 節點衝突。若存在外部 `roscore`，GUI 會重用它。
2. 開啟「01 專案設定」：
   - Autoware 工作空間：`~/autoware.ai`
   - LiDAR ROS bag：`/mnt/d/VLP16/mapping.bag`
   - PCD 地圖：`~/autoware.ai/maps/vlp16_ndt_01.pcd`
   - CSV 目錄：`~/autoware.ai/trajectory`
   - LiDAR 外參：本次測試可先用全零，但這**不是** Hunter 上 VLP-16 的實際校正值。
3. 按「檢查路徑與 ROS」檢查目前設定。

### ROS 時間與 TF

- GUI 會設定 `/use_sim_time=true`，並以 `rosbag play --clock` 發布錄製時間。
- GUI 會設定 `/localizer=velodyne`、`/tf_x` 至 `/tf_yaw`，並發布 `base_link → velodyne` 靜態 TF。
- 以上 ROS 參數屬於目前 ROS Master 的**全域狀態**。若其他實驗正在使用相同 Master，請先與操作者協調。
- 原本 `tf_x is not set` 引發的啟動問題，已在 GUI 的節點啟動流程中透過預先設定參數處理。

## 三、NDT Mapping（建立地圖）

1. 前往「02 NDT 建圖」，可以先在「NDT 核心參數」調整 Resolution、Step Size、Transformation Epsilon、最大迭代次數，以及 Voxel Leaf Size、Min/Max Scan Range、Min Add Scan Shift。按 **儲存目前參數**，然後按 **啟動建圖環境**。
2. 檢查 `NDT Mapping` 狀態及下方 ROS 紀錄：GUI 會先等待 `/ndt_mapping` 訂閱 `/config/ndt_mapping`，再發布這一次啟動時保存的參數。待看到「參數發布程序已完成」後，按 **開啟 RViz** 可以觀察 `/ndt_map`。
3. 按 **載入 Bag（暫停）**。
   - 「執行紀錄 / ROS 輸出」上方有一行即時播放狀態，例如 `[PAUSED] Bag Time: ... Duration: 0.00 / 49.21 s`。播放後更新為 `[RUNNING]`，**同一行持續刷新而不增加大量訊息**。
4. 可選擇進入「04 路徑與輸出」按 **開始錄製 CSV**，用來保存 `/current_pose`，再回建圖頁。
5. 按 **播放 / 暫停** 開始播放，等待 489 筆 bag 掃描處理完畢。終端輸出中的 processed/input 數量應持續增加。
6. 設定 PCD 濾波解析度，例如 `0.20 m`，按 **儲存 PCD**。
7. 查看下方執行紀錄，並以 RViz 驗證地圖。請確認 PCD 路徑下有非零大小的點雲檔案。
8. 若有錄製 CSV，按 **停止並整理 CSV**；若要切換到定位，先停止建圖節點。

本次已成功的 PCD 檔案為 `~/autoware.ai/maps/vlp16_ndt_01.pcd`，範例約 36,328 points。**請注意：若重複按「儲存 PCD」，GUI 會先詢問是否覆寫。**

## 四、NDT Matching（使用既有 PCD 定位）

1. 回到建圖頁先按 **停止建圖節點**，確定狀態已關閉。
2. 前往「03 NDT 定位」，可先調整 **Resolution、Step Size、Transformation Epsilon、Max Iterations**，按 **儲存目前參數** 和 **啟動定位環境**。
3. GUI 將用 PCD 發布 `/points_map`，並啟動：

   ```bash
   roslaunch lidar_localizer ndt_matching.launch method_type:=0 use_gnss:=false use_odom:=false use_imu:=false
   ```

4. GUI 會等待 `/ndt_matching` 訂閱 `/config/ndt`，再發布本次保存的 NDT 參數；bag 第一次開始播放後，會用**同一組啟動參數**再次發布初始位姿（地圖原點），不會將你調過的解析度或迭代次數改回預設值。必要時可按 **重設起點 (0,0,0)**。
5. 按 **載入 Bag（暫停）**。定位模式會把 bag 的 `/points_raw` 重新映射為 `/filtered_points`。
6. **先前往「04 路徑與輸出」按「開始錄製 CSV」**，再回定位頁開始播放。
7. 按 **播放 / 暫停**，建議使用 `0.2×` 先確認 `/ndt_pose`、`/ndt_stat` 正常輸出。
8. 播放結束，回到輸出頁按 **停止並整理 CSV**。這一步會把 raw CSV 的四元數換算成 RPY。

定位初始化假設 bag 的起點與原先的建圖起點重合；如果以不同起點或不同地圖執行，需要擴充初始位姿設定及驗證。

### CSV 輸出檔案

例如：

```
~/autoware.ai/trajectory/
  ndt_matching_20261117_170000_raw.csv
  ndt_matching_20261117_170000.csv
  ndt_matching_20261117_170000_stat.csv
```

整理後的軌跡欄位：

```
time_s,ros_time_s,x,y,z,roll,pitch,yaw,yaw_deg
```

- `time_s`：從**第一筆成功記錄的位姿**開始算的相對秒數。
- `ros_time_s`：ROS 訊息接收／記錄時間（秒）。
- `x,y,z`：地圖座標（m）。
- `roll,pitch,yaw`：姿態角（rad）。
- `yaw_deg`：航向角（degree）。
- `*_stat.csv`：保留原始 `/ndt_stat`，可以分析執行時間、NDT Fitness Score、迭代次數。

**注意**：原始 bag 只有 `/points_raw`，並沒有 `/ndt_pose`，因此**不可能等 bag 全部播放完，才開始記錄而補回完整軌跡**。請先按「開始錄製 CSV」，再按播放。如果漏錄，須重新播放 bag。

## 五、重新啟動後套用 NDT 參數

這個學生版 GUI 採用**調整、儲存、停止節點、重新啟動後套用**的流程；與 Autoware Runtime Manager 使用相同的 ROS 設定 Topic，但不會在學生修改輸入框時自動發送變更。

| 運作模式 | 設定 Topic | GUI 可編輯參數 |
| --- | --- | --- |
| NDT Mapping | `/config/ndt_mapping` | Resolution、Step Size、Transformation Epsilon、Max Iterations、Voxel Leaf Size、Min/Max Scan Range、Min Add Scan Shift |
| NDT Matching | `/config/ndt` | Resolution、Step Size、Transformation Epsilon、Max Iterations |

建議讓學生每次只調整一個參數，並比較重新運算後的 PCD、`/ndt_stat`、CSV 軌跡及執行時間。

- 修改 GUI 數值時，**正在運作的節點仍使用舊參數**。先按對應的「停止建圖／定位節點」，再按「啟動建圖／定位環境」。
- GUI 會把數值保存到 QSettings，下一次開啟 GUI 仍保留上次輸入；按「還原此頁預設值」可回到原始設定。
- 新啟動的 Mapping／Matching 會在 ROS 節點及參數 Topic 訂閱端出現後，自動發布 ConfigNDTMapping／ConfigNDT；**請先確認下方日誌顯示發布成功，才開始播放 Bag。**
- Mapping 的 **NDT Resolution** 控制點雲配準時的 NDT 網格；下方 **PCD 濾波解析度** 只影響地圖輸出後的降採樣，兩者作用不同。
- 源碼 `ndt_mapping.cpp` 的 `leaf_size` 預設為 2.0 m；GUI 沿用此值（不要與其他版本 Runtime Manager 介面可能顯示的 1.0 m 混淆）。
- CPU/GPU 方法、IMU/Odom、TF 外參不是這一批可以調整的核心 NDT 設定。此教學版仍沿用 CPU method_type=0、無 GNSS/IMU/Odom 的已測試配置。
- 更改 Matching 參數時，務必保留 `init_pos_gnss=0` 和既定初始位姿；本 GUI 會自動維持這些欄位，避免重新初始化為不預期的位置。
- **實測狀態：**本次 WSL ROS Melodic 已透過 GUI 成功發布 NDT 參數、執行 Mapping／Matching 並接通離線導航；不同 bag、不同電腦與不同 ROS 安裝仍須個別驗證。

## 六、Waypoint 與離線 Pure Pursuit（新增 05 頁籤）

此頁先驗證離線 **Waypoint → 路徑追蹤指令**。沒有 CAN／USB 連接 Hunter，也沒有實車底盤驅動。在這階段輸出的速度指令只是用來分析演算法，**不代表已可讓車自動行駛**。

### 1. 產生或選擇 Waypoint

1. 本次已驗證 `~/autoware.ai/trajectory/vlp16_waypoints_01_lf.csv`，可直接填到「Waypoint CSV」，按「檢查 Waypoint CSV」。需採 **LF 行尾**，避免 `waypoint_loader` 在 CRLF 的 `change_flag` 欄位上以 `std::stoi` 崩潰；不用每次重播 bag 才重新轉換。
2. 若想重新產生：在「NDT 軌跡 CSV」選 `ndt_matching_...csv`（**不是** `_raw.csv` 或 `_stat.csv`），設定 0.5 m、2.0 km/h、最大跳點 1.5 m；輸出改成尚未存在的檔名，例如 `vlp16_waypoints_02.csv`，按「產生 Waypoint CSV」。
3. 成功時可看到 Waypoint 點數與估計路徑長度。你目前的實例為 237 筆輸入 → 49 點，長度約 27.55 m；中位 yaw／切線差約 6°，適合進入**離線功能驗證**，不等於可實車行駛。

### 2. 啟動 ROS 節點

1. 在「03 NDT 定位」啟動 NDT Matching、載入 PCD，等待啟動參數發送成功。**此步無需先按播放**。
2. 在「05 Waypoint / 導航測試」按「載入 Waypoint」。GUI 先啟動 Python 2 `offline_nav_bridge.py`，隨後執行 `rosrun waypoint_maker waypoint_loader _multi_lane_csv:=...`。
3. 按「檢查導航 Topics」，確認 `/based/lane_waypoints_raw` 與 `/offline_nav/final_waypoints` 已列出。`rostopic list` 僅能證明 Topic 存在，若仍沒有資料，需要進一步 `rostopic echo -n 1`。
4. 按「啟動 Pure Pursuit + Filter」。GUI 會啟動專屬 launch，把 Pure Pursuit、Twist Filter 的輸出重新映射至 `/offline_nav/twist_raw` 和 `/offline_nav/twist_cmd`，並發送 Lookahead 與濾波設定。
5. 回「03 NDT 定位」按「載入 Bag（暫停）」，再按播放。**要確定 /ndt_pose 持續發布時，才有即時位置供追蹤器計算**。
6. 返回「05」按「檢查導航 Topics」，再按「讀取一筆 Twist 指令」；輸出會顯示在下方 ROS 紀錄（若沒有資料，該取樣程序會等待下一筆）。
7. 按「停止導航測試」停止由此面板啟動的 Waypoint 與導航節點；NDT Matching 和 Bag 可由原有頁面各自停止。

### 2.1 RViz 導航驗證（已在 WSL 實測）

1. 在「05 Waypoint / 導航測試」按 **「開啟導航 RViz」**，會自動載入 `rviz/navigation.rviz`。
2. 固定座標系為 `map`；`Waypoint Path (full)` 顯示 `/offline_nav/waypoint_path` 的完整路線，`NDT Pose` 顯示 `/ndt_pose`。
3. 查看 `Lookahead Target`、`Next Waypoint`、`Lookahead Search Circle` 與 `Pursuit Trajectory` 等 Pure Pursuit Marker，觀察目標點隨定位位姿移動。
4. 在外部 WSL 終端機用 `rostopic echo /offline_nav/twist_cmd/twist/linear/x` 觀察末段速度。本次範例從 `0.555555555556 m/s` 變成連續 `0.0 m/s`，代表離線零速命令確實發布；**不代表實車完成停車或定量終點誤差通過**。

原版 Autoware 某些 Marker 可能在 RViz 顯示 `Uninitialized quaternion, assuming identity`。若 marker 的位置、追蹤點和速度輸出正常，這通常是 Marker 姿態初始化警告，並非純粹因該警告就能判斷追蹤失敗。

### 3. 這一階段的 Topic 設計

| 輸入／輸出 | ROS Topic | 備註 |
| --- | --- | --- |
| Waypoint v3 CSV | `/based/lane_waypoints_raw` | 官方 `waypoint_loader` 發布 LaneArray |
| 完整路線顯示 | `/offline_nav/waypoint_path` | `nav_msgs/Path`，由 bridge 保留完整路徑供 RViz 顯示 |
| Pure Pursuit 前方路線 | `/offline_nav/final_waypoints` | bridge 發布首條 Lane 的前方區段，**未經障礙物速度規劃** |
| 當前位置 | `/offline_nav/current_pose` | 轉送 NDT `/ndt_pose`；未驗證實車 base_link 外參 |
| 速度估計 | `/offline_nav/current_velocity` | 優先沿用 `/estimate_twist`，否則用 NDT 位移差分近似 |
| Pure Pursuit 原始命令 | `/offline_nav/twist_raw` | 不會送到 `/twist_raw` 或馬達 |
| Twist Filter 命令 | `/offline_nav/twist_cmd` | 不會送到 `/twist_cmd` 或馬達 |
| 離線控制命令 | `/offline_nav/ctrl_cmd` | 另行隔離 C++ 節點可能輸出的 ControlCommand topic，不送到全域 `/ctrl_cmd` |

此示範未建置 `lane_rule`、`lane_select`、`astar_avoid`、`velocity_set` 等規劃節點，也不會驗證交通規則、障礙物或緊急停止。若要朝實車導航擴充，之後須確認 Hunter 具體車型、轉向模型、CAN 驅動、急停及障礙物處理。

### 4. 如果沒有 Twist 輸出

在 WSL 同一工作空間測試：

```bash
source ~/autoware.ai/install/setup.bash
rosnode list | grep -E 'offline_nav_bridge|waypoint_loader|offline_pure_pursuit|offline_twist_filter'
rostopic info /based/lane_waypoints_raw
rostopic info /offline_nav/final_waypoints
rostopic info /offline_nav/current_pose
rostopic info /offline_nav/twist_raw
rostopic info /offline_nav/twist_cmd
```

如果沒有 `/offline_nav/current_pose` 的訊息，先查 `/ndt_pose` 與 Bag `/clock`；如果沒有 `/offline_nav/final_waypoints` 訊息，先看 `waypoint_loader` 的 ROS 日誌。有 Node 或 Topic 不代表必定已經發布資料，請用 `rostopic echo -n 1` 確認。

**實測狀態**：本次已在 Windows 11／WSL2／ROS Melodic 實際跑通 Waypoint → Pure Pursuit → Twist Filter；示範 49 點、約 27.44 m，命令速度約 `0.55556 m/s`，末段可輸出 `0.0 m/s`。若 `twist_raw` 有角速度但 `twist_cmd` 的角速度全為零，確認 GUI 已發布完整 `/offline_nav/config/twist_filter`，尤其 **`lateral_jerk_limit=5.0`**。這僅是離線 ROS 命令流程，不包含真車控制與安全測試。

## 七、使用限制與注意事項

- GUI 只是控制介面，是否成功還是依賴 ROS、Autoware 的執行環境與資料格式。
- 下方「執行紀錄 / ROS 輸出」會將 ROS1 `rosbag play` 的 `[RUNNING]/[PAUSED] Bag Time ... Duration ...` 解析後顯示在**固定一行**，不將每次時間更新追加到文字紀錄。文字紀錄預設保留 Bag 錯誤與警告，以及每 50 筆的 Mapping 摘要。要排查其他 ROS 訊息時，可勾選「顯示詳細日誌」，但 Bag 時間仍只佔固定一行。
- 此程式針對本次已測試過的單 LiDAR bag；未檢驗其他 ROS bag、改動過的話題名稱、雙 LiDAR 或多感測器情境。
- 原始 bag 只有 VLP-16 點雲，沒有 Odom、IMU、GNSS；預設匹配不依賴這些感測器。
- 使用同一份資料建圖並回放定位，僅是「流程可行」的測試；不能等同跨資料集或實機導航性能驗證。
- 你先前 `/ndt_stat` 曾觀察到 `exe_time≈330 ms`，而 VLP-16 資料約 10 Hz，後續若希望原速執行，仍要評估計算延遲及積壓。
- `Use Sim Time` 為 true 時，必須播放具有 `--clock` 的 bag，某些程序在模擬時間尚未開始時可能等待。初始位姿若未生效，請開始播放後再按一次「重設起點」。
- Ubuntu 18.04 / ROS Melodic 已停止一般維護，請把本環境視為**隔離的教學實驗系統**，避免直接曝露在不受控網路。
- 關閉 GUI 時會要求停止由本 GUI 啟動的程序，不會主動停止在 GUI 外部啟動的 ROS Master。
- 若使用 WSL2，按「開啟軌跡資料夾」會透過 `explorer.exe` 打開 Windows 檔案總管，不需要安裝 Linux 檔案管理器或 `xdg-open`。若 Windows 程序互通功能被停用，請檢查 WSL interop 設定。
- Bag 播放／停止時所用的 PTY 是整數檔案描述符；此版本在結束時使用 `os.close()` 清理，避免舊版 `AttributeError: 'int' object has no attribute 'close'` 反覆出現。`gedit` 找不到 Adwaita 圖示或無法保存編輯器 metadata 的警告，不是 Autoware 或 GUI 節點錯誤。

## 八、驗證 GUI 程式本身（不需要 ROS）

在解壓縮的資料夾下執行：

```bash
python3 -m unittest discover -s tests -v
```

以上測試檢查 WSL 路徑轉換、shell 路徑引用、TF 參數順序、NDT Mapping／Matching 訊息內容及參數驗證、Pose CSV 輸出格式等；單元測試本身不等於 ROS 端到端測試，但**本次另外已有人工在 WSL 執行上述離線導航流程**。

## 九、後續滾動擴充方向

- 可讓使用者設定非零的初始地圖位姿，並於同一套參數紀錄中保存每次試驗的設定快照。
- 自動保存完整執行設定（JSON）、定位結果和檢查表。
- NDT 軌跡疊圖、Fitness Score 趨勢、時間與點雲資料數量比較。
- 動態路徑規劃／障礙物避障、Hunter 實機控制（需要另外進行安全及整合驗證）。

## 主要檔案

```
Autoware_GUI/
  autoware_student_gui.py   # PyQt5 GUI 與 ROS 子程序控制
  aw_gui_core.py            # ROS 命令、路徑、CSV 換算
  convert_ndt_to_waypoints.py # NDT CSV → Waypoint v3 CSV
  offline_nav_bridge.py    # ROS Melodic Python2 離線 Topic 橋接
  launch/
    offline_pure_pursuit.launch # 隔離的 PP + Twist Filter ROS 節點
  rviz/
    mapping.rviz           # 建圖 RViz 預設畫面
    matching.rviz          # 定位 RViz 預設畫面
    navigation.rviz        # 導航路徑、NDT Pose、Pure Pursuit 標記
  tests/
    test_core.py           # 不需要 ROS/Qt 的單元測試
  README.md                # 本操作說明
```
