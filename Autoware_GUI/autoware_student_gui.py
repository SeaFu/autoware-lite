#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Autoware.AI 1.14 + ROS Melodic student GUI (offline bag workflow).

Runs INSIDE Ubuntu 18.04 WSL2, using PyQt5. ROS commands are subprocesses,
so this program uses Python 3 without interfering with ROS Melodic's Python 2.
"""

import datetime
import glob
import json
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import time

from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from aw_gui_core import (
    MAP_OUTPUT_TYPE, NDT_CONFIG_TYPE, compact_ros_lines, convert_pose_csv,
    fmt_number, inspect_waypoint_csv, linux_path, mapping_config, match_config, ndt_config_command,
    parse_bag_progress, shell_command, tf_arguments,
)


APP_ROOT = os.path.dirname(os.path.abspath(__file__))
COLOR_OK, COLOR_WARN, COLOR_OFF = "#38d9b1", "#f4c76e", "#8795a8"
DEFAULT_UI_FONT_PX = 17


class OwnedProcess:
    """A process group this GUI started and is allowed to signal."""

    def __init__(self, name, proc, stream=None, stdin_pty=None, output_file=None):
        self.name = name
        self.proc = proc
        self.stream = stream
        self.stdin_pty = stdin_pty
        self.output_file = output_file
        self.stopping = False
        self.bag_status_buffer = ""

    def alive(self):
        return self.proc.poll() is None

    def stop(self):
        if self.alive():
            self.stopping = True
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGINT)
            except (OSError, ProcessLookupError):
                pass

    def close_files(self):
        # rosbag playback uses a PTY: stream and stdin_pty may be the SAME
        # integer file descriptor. Close it exactly once via os.close().
        pty_fd = self.stdin_pty
        if self.stdin_pty is not None:
            try:
                os.close(self.stdin_pty)
            except OSError:
                pass
            self.stdin_pty = None
        if self.output_file:
            try:
                self.output_file.flush()
                self.output_file.close()
            except (OSError, ValueError):
                pass
            self.output_file = None
        if self.stream is not None:
            try:
                if isinstance(self.stream, int):
                    if self.stream != pty_fd:
                        os.close(self.stream)
                else:
                    self.stream.close()
            except (OSError, ValueError):
                pass
            self.stream = None


class StudentGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hunter - Autoware.AI GUI")
        self.resize(1280, 900)
        self.settings = QSettings("NTUT-Robotics", "AutowareStudentGUI")
        self.processes = {}
        self.mode = None
        self.bag_paused = False
        self.bag_started = False
        self.pose_initialized_for_bag = False
        self.last_bag_progress = None
        self.pending_mode = None
        self.core_deadline = 0.0
        self.last_capture = None
        self.active_capture = None
        self.ndt_fields = {}
        self.ndt_hints = {}
        self.active_ndt_configs = {}
        self.ndt_config_ready = set()
        self.create_ui()
        self.load_settings()
        self.suggest_nav_input()
        self.poller = QTimer(self)
        self.poller.timeout.connect(self.poll_processes)
        self.poller.start(200)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(900)
        self.message("面板就緒。請先停止手動啟動的 ndt_mapping、ndt_matching 與 rosbag，避免重複節點。")

    # ----- UI --------------------------------------------------------------
    def create_ui(self):
        # The size tokens are replaced together so no widget is left with a
        # tiny font when students enlarge text from the header control.
        self.ui_style_template = """
            QMainWindow, QWidget { background:#101826; color:#eaf1f9; font-family:'Noto Sans CJK TC','Microsoft JhengHei',sans-serif; font-size:__BASE__px; }
            QGroupBox { background:#1a2637; border:1px solid #304158; border-radius:11px; margin-top:18px; padding:16px 13px 14px; font-weight:600; font-size:__BASE__px; }
            QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 8px; color:#d3e4fc; }
            QLineEdit, QDoubleSpinBox, QSpinBox { background:#111b2b; border:1px solid #40516a; border-radius:7px; padding:8px 10px; color:#f5f8ff; min-height:23px; }
            QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus { border:1px solid #3bc7a9; }
            QPushButton { background:#30445e; color:white; border:1px solid #45607c; border-radius:8px; padding:10px 15px; font-weight:600; min-height:23px; }
            QPushButton:hover { background:#3c5674; }
            QPushButton:disabled { background:#243246; color:#778a9f; border:1px solid #304155; }
            QPushButton[accent="true"] { background:#087e82; border:1px solid #22b5ad; }
            QPushButton[accent="true"]:hover { background:#0f9ca0; }
            QPushButton[danger="true"] { background:#6d343b; border-color:#99535a; }
            QTextEdit { background:#0a1320; border:1px solid #324358; border-radius:9px; font-family:'DejaVu Sans Mono',monospace; font-size:__LOG__px; }
            QTabWidget::pane { border:1px solid #33465e; border-radius:8px; }
            QTabBar::tab { background:#1d2a3c; color:#b8c8da; padding:12px 22px; border:1px solid #314258; font-size:__BASE__px; }
            QTabBar::tab:selected { background:#254b61; color:#ffffff; }
            QScrollArea { border:0px; }
            QLabel#hint { color:#a6b7cb; }
            QLabel#appTitle { color:#53e2cf; font-size:__TITLE__px; font-weight:800; }
            QLabel#appSubtitle { color:#a9bad0; font-size:__SUBTITLE__px; }
            QFrame#statusbar { background:#182637; border:1px solid #34485f; border-radius:9px; }
            QToolTip { font-size:__BASE__px; background:#1a2637; color:#eaf1f9; border:1px solid #45607c; padding:6px; }
        """
        main = QWidget()
        self.setCentralWidget(main)
        whole = QVBoxLayout(main)
        whole.setContentsMargins(20, 16, 20, 16)
        title = QLabel("HUNTER  /  AUTOWARE.AI")
        title.setObjectName("appTitle")
        subtitle = QLabel("ROS1 Melodic · Ubuntu 18.04 WSL2 · VLP-16 離線建圖與定位教學")
        subtitle.setObjectName("appSubtitle")
        header = QHBoxLayout()
        header_title = QVBoxLayout()
        header_title.addWidget(title)
        header_title.addWidget(subtitle)
        header.addLayout(header_title)
        header.addStretch()
        header.addWidget(QLabel("介面字級"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(14, 22)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setToolTip("調整整個 GUI 的字級（包含 ROS 輸出）；會自動記住設定。")
        self.font_size_spin.setFixedWidth(110)
        header.addWidget(self.font_size_spin)
        whole.addLayout(header)
        bar = QFrame()
        bar.setObjectName("statusbar")
        row = QHBoxLayout(bar)
        self.badges = {}
        for key, label in (("core", "ROS Master"), ("tf", "TF"), ("mapping", "NDT Mapping"),
                           ("matching", "NDT Matching"), ("bag", "Bag"),
                           ("csv", "CSV"), ("nav", "Nav Test")):
            badge = QLabel(label + "  ● 未啟動")
            badge.setStyleSheet("color:" + COLOR_OFF + "; font-weight:600; padding:3px")
            row.addWidget(badge)
            self.badges[key] = (badge, label)
        whole.addWidget(bar)
        splitter = QSplitter(Qt.Vertical)
        whole.addWidget(splitter, 1)
        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)
        self.tabs.addTab(self.build_setup_tab(), "01  專案設定")
        self.tabs.addTab(self.build_mapping_tab(), "02  NDT 建圖")
        self.tabs.addTab(self.build_matching_tab(), "03  NDT 定位")
        self.tabs.addTab(self.build_output_tab(), "04  路徑與輸出")
        self.tabs.addTab(self.build_navigation_tab(), "05  Waypoint / 導航測試")
        log_wrap = QWidget()
        log_layout = QVBoxLayout(log_wrap)
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("執行紀錄 / ROS 輸出"))
        log_header.addStretch()
        self.verbose_logs = QCheckBox("顯示詳細日誌")
        self.verbose_logs.setChecked(False)
        self.verbose_logs.setToolTip("預設過濾 Bag 進度及 NDT 每筆掃描的重複輸出；勾選後查看詳細 ROS 日誌。")
        log_header.addWidget(self.verbose_logs)
        clear = self.button("清空紀錄", lambda: self.logs.clear())
        log_header.addWidget(clear)
        log_layout.addLayout(log_header)
        self.bag_time_label = QLabel("Bag：尚未載入")
        self.bag_time_label.setStyleSheet(
            "background:#0a1320; border:1px solid #324358; border-radius:7px; "
            "padding:6px 11px; color:#53e2cf; font-family:'DejaVu Sans Mono',monospace;"
        )
        self.bag_time_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        log_layout.addWidget(self.bag_time_label)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.document().setMaximumBlockCount(850)
        log_layout.addWidget(self.logs)
        splitter.addWidget(log_wrap)
        splitter.setSizes([555, 215])
        bottom = QHBoxLayout()
        self.workflow_label = QLabel("目前模式：尚未選擇")
        bottom.addWidget(self.workflow_label)
        bottom.addStretch()
        bottom.addWidget(self.button("停止本面板啟動的所有節點", self.stop_all, danger=True))
        whole.addLayout(bottom)
        try:
            saved_font_px = int(self.settings.value("ui_font_px", DEFAULT_UI_FONT_PX))
        except (ValueError, TypeError):
            saved_font_px = DEFAULT_UI_FONT_PX
        self.font_size_spin.setValue(max(14, min(22, saved_font_px)))
        self.font_size_spin.valueChanged.connect(self.apply_text_size)
        self.apply_text_size(self.font_size_spin.value())

    def apply_text_size(self, size):
        """Scale all GUI text at once without changing any ROS behavior."""
        size = int(size)
        stylesheet = self.ui_style_template
        for token, value in (("__BASE__", size), ("__LOG__", max(12, size - 2)),
                             ("__TITLE__", size + 11), ("__SUBTITLE__", max(13, size - 2))):
            stylesheet = stylesheet.replace(token, str(value))
        self.setStyleSheet(stylesheet)
        self.settings.setValue("ui_font_px", size)

    def button(self, caption, callback, accent=False, danger=False):
        btn = QPushButton(caption)
        btn.setProperty("accent", accent)
        btn.setProperty("danger", danger)
        btn.clicked.connect(callback)
        return btn

    def field_with_browse(self, default, is_directory=False, is_file=True):
        line = QLineEdit(default)
        line.setMinimumWidth(430)
        btn = self.button("瀏覽…", lambda: self.browse(line, is_directory, is_file))
        wrap = QWidget()
        l = QHBoxLayout(wrap)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(line, 1)
        l.addWidget(btn)
        return line, wrap

    def browse(self, line, directory, input_file):
        cur = linux_path(line.text())
        if directory:
            result = QFileDialog.getExistingDirectory(self, "選取資料夾", cur)
        elif input_file:
            result, _ = QFileDialog.getOpenFileName(self, "選取檔案", cur)
        else:
            result, _ = QFileDialog.getSaveFileName(self, "儲存檔案", cur)
        if result:
            line.setText(result)

    def pane(self, label, hint=None):
        gb = QGroupBox(label)
        layout = QVBoxLayout(gb)
        if hint:
            tip = QLabel(hint)
            tip.setWordWrap(True)
            tip.setObjectName("hint")
            layout.addWidget(tip)
        return gb, layout

    def scroll_widget(self, content):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(content)
        return area

    def build_setup_tab(self):
        content = QWidget()
        v = QVBoxLayout(content)
        project, box = self.pane("工作空間與輸入資料", "檔案路徑使用 WSL Linux 格式；可貼入 D:\\VLP16\\mapping.bag，會自動轉成 /mnt/d/...")
        form = QFormLayout()
        self.workspace, widget = self.field_with_browse("~/autoware.ai", True)
        form.addRow("Autoware 工作空間", widget)
        self.bag_path, widget = self.field_with_browse("/mnt/d/VLP16/mapping.bag")
        form.addRow("LiDAR ROS bag", widget)
        self.map_path, widget = self.field_with_browse("~/autoware.ai/maps/vlp16_ndt_01.pcd", False, False)
        form.addRow("PCD 地圖路徑", widget)
        self.csv_folder, widget = self.field_with_browse("~/autoware.ai/trajectory", True)
        form.addRow("軌跡輸出資料夾", widget)
        box.addLayout(form)
        v.addWidget(project)
        extr, extr_box = self.pane("LiDAR 外參 / base_link → velodyne", "目前測試使用全零外參。Hunter 實機的真實安裝外參必須量測後填入，不能把這組零值當作校正結果。")
        grid = QGridLayout()
        self.extra_fields = {}
        for i, (k, caption) in enumerate((("x", "X (m)"), ("y", "Y (m)"), ("z", "Z (m)"),
                                          ("roll", "Roll (rad)"), ("pitch", "Pitch (rad)"), ("yaw", "Yaw (rad)"))):
            spin = QDoubleSpinBox()
            spin.setRange(-1000, 1000)
            spin.setDecimals(5)
            spin.setSingleStep(0.05)
            spin.setValue(0)
            self.extra_fields[k] = spin
            r, c = divmod(i, 3)
            grid.addWidget(QLabel(caption), r*2, c)
            grid.addWidget(spin, r*2+1, c)
        extr_box.addLayout(grid)
        v.addWidget(extr)
        row = QHBoxLayout()
        row.addWidget(self.button("檢查路徑與 ROS", self.check_environment, accent=True))
        row.addWidget(self.button("啟動 / 重用 ROS Master", self.ensure_core_only))
        row.addWidget(self.button("儲存設定", self.save_settings))
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        return self.scroll_widget(content)

    def build_mapping_tab(self):
        content = QWidget()
        v = QVBoxLayout(content)
        group, l = self.pane("① NDT Mapping", "自動設定 ROS 參數、發布 LiDAR TF，並啟動 CPU 版 NDT Mapping。只使用 VLP-16 /points_raw，不需要 IMU 或 odom。")
        row = QHBoxLayout()
        row.addWidget(self.button("啟動建圖環境", lambda: self.prepare_mode("mapping"), accent=True))
        row.addWidget(self.button("停止建圖節點", lambda: self.stop_mode("mapping"), danger=True))
        row.addWidget(self.button("開啟 RViz", self.open_rviz))
        l.addLayout(row)
        v.addWidget(group)
        v.addWidget(self.build_ndt_parameters("mapping"))
        v.addWidget(self.build_bag_card("mapping"))
        output, l = self.pane("④ 匯出點雲地圖", "建圖完成後輸出 PCD；NDT 累積地圖與匯出後的降採樣點數通常不同。請先檢查結果，再用它進行 NDT Matching。")
        row = QHBoxLayout()
        row.addWidget(QLabel("PCD 濾波解析度 (m)"))
        self.pcd_resolution = QDoubleSpinBox()
        self.pcd_resolution.setRange(0.01, 5.0)
        self.pcd_resolution.setDecimals(2)
        self.pcd_resolution.setValue(0.20)
        self.pcd_resolution.setSingleStep(0.05)
        row.addWidget(self.pcd_resolution)
        row.addWidget(self.button("儲存 PCD", self.export_pcd, accent=True))
        row.addStretch()
        l.addLayout(row)
        v.addWidget(output)
        v.addStretch()
        return self.scroll_widget(content)

    def build_matching_tab(self):
        content = QWidget()
        v = QVBoxLayout(content)
        group, l = self.pane("① NDT Matching", "載入 PCD → /points_map；使用 CPU NDT (method_type=0)、use_gnss=false、use_odom=false、use_imu=false。")
        row = QHBoxLayout()
        row.addWidget(self.button("啟動定位環境", lambda: self.prepare_mode("matching"), accent=True))
        row.addWidget(self.button("重設起點 (0,0,0)", self.publish_initial_pose))
        row.addWidget(self.button("停止定位節點", lambda: self.stop_mode("matching"), danger=True))
        row.addWidget(self.button("開啟 RViz", self.open_rviz))
        l.addLayout(row)
        v.addWidget(group)
        v.addWidget(self.build_ndt_parameters("matching"))
        v.addWidget(self.build_bag_card("matching"))
        output, l = self.pane("④ 定位輸出", "啟動 bag 後，NDT Matching 會透過 /ndt_pose 發布位姿；在輸出頁籤可以記錄軌跡、Fitness Score 與定位耗時。")
        self.ndt_note = QLabel("建議先以 0.2× 進行離線測試；正式實機 10 Hz 資料需另外確認 CPU 是否來得及處理。")
        self.ndt_note.setWordWrap(True)
        l.addWidget(self.ndt_note)
        row = QHBoxLayout()
        row.addWidget(self.button("檢查 /ndt_pose", self.check_pose_topic))
        row.addWidget(self.button("前往軌跡紀錄", lambda: self.tabs.setCurrentIndex(3), accent=True))
        row.addStretch()
        l.addLayout(row)
        v.addWidget(output)
        v.addStretch()
        return self.scroll_widget(content)

    def build_ndt_parameters(self, mode):
        mapping = mode == "mapping"
        defaults = mapping_config() if mapping else match_config()
        labels = (
            ("resolution", "NDT Resolution (m)", 0.05, 10, 0.1,
             "NDT 分布網格大小；不是輸出 PCD 的濾波解析度。"),
            ("step_size", "Step Size (m)", 0.001, 5, 0.01,
             "NDT 最佳化每步的搜尋尺度。"),
            ("trans_epsilon", "Transformation Epsilon", 0.00001, 1, 0.001,
             "相鄰兩次估計位姿的收斂門檻。"),
            ("max_iterations", "Max Iterations", 1, 300, 1,
             "單次 NDT 配準允許的最大迭代次數。"),
        )
        if mapping:
            labels += (
                ("leaf_size", "Scan Voxel Leaf (m)", 0.05, 10, 0.1,
                 "進入 NDT 前對每幀掃描點雲進行降採樣。"),
                ("min_scan_range", "Min Scan Range (m)", 0, 100, 0.5,
                 "忽略距 LiDAR 太近的點。"),
                ("max_scan_range", "Max Scan Range (m)", 0.1, 300, 1,
                 "忽略距 LiDAR 太遠的點。"),
                ("min_add_scan_shift", "Min Add Scan Shift (m)", 0, 10, 0.1,
                 "累積地圖新增掃描所需的最小位移。"),
            )
        group, box = self.pane(
            "② NDT 核心參數（下次啟動生效）",
            "先調整數值，然後停止並重新啟動此頁的 NDT 節點；GUI 會自動發送完整設定。"
            "運行中的節點不會因改動輸入框而立即修改參數。",
        )
        grid = QGridLayout()
        self.ndt_fields[mode] = {}
        for i, (name, caption, low, high, step, tooltip) in enumerate(labels):
            if name == "max_iterations":
                spin = QSpinBox()
                spin.setRange(int(low), int(high))
            else:
                spin = QDoubleSpinBox()
                spin.setRange(low, high)
                spin.setDecimals(5)
                spin.setSingleStep(step)
            spin.setValue(defaults[name])
            spin.setToolTip(tooltip)
            spin.valueChanged.connect(lambda _value, m=mode: self.mark_ndt_pending(m))
            self.ndt_fields[mode][name] = spin
            row, col = divmod(i, 3)
            grid.addWidget(QLabel(caption), row*2, col)
            grid.addWidget(spin, row*2+1, col)
        box.addLayout(grid)
        actions = QHBoxLayout()
        actions.addWidget(self.button("儲存目前參數", self.save_settings, accent=True))
        actions.addWidget(self.button("還原此頁預設值", lambda _checked=False, m=mode: self.reset_ndt_parameters(m)))
        actions.addStretch()
        box.addLayout(actions)
        state = QLabel("尚未啟動：這些數值會在下一次啟動時送入 NDT 節點。")
        state.setWordWrap(True)
        state.setObjectName("hint")
        box.addWidget(state)
        self.ndt_hints[mode] = state
        return group

    def ndt_parameter_values(self, mode):
        values = {name: widget.value() for name, widget in self.ndt_fields[mode].items()}
        return mapping_config(values) if mode == "mapping" else match_config(values)

    def mark_ndt_pending(self, mode):
        if mode not in self.ndt_hints:
            return
        self.ndt_hints[mode].setText(
            "已修改參數：請停止並重新啟動 NDT 節點才會套用。"
            if self.alive(mode) else "準備就緒：下一次啟動節點會使用目前參數。"
        )

    def reset_ndt_parameters(self, mode):
        defaults = mapping_config() if mode == "mapping" else match_config()
        for name, widget in self.ndt_fields[mode].items():
            widget.setValue(defaults[name])
        self.mark_ndt_pending(mode)
        self.message("已還原 {} 的預設 NDT 參數；重新啟動節點後生效。".format(mode))

    def build_bag_card(self, mode):
        group, box = self.pane("③ ROS bag 播放器", "從暫停狀態啟動，按播放／暫停切換。定位模式將 /points_raw 映射到 /filtered_points；建圖模式保持 /points_raw。")
        row = QHBoxLayout()
        row.addWidget(QLabel("播放倍率"))
        speed = QDoubleSpinBox()
        speed.setRange(0.1, 2.0)
        speed.setDecimals(1)
        speed.setSingleStep(0.1)
        speed.setValue(0.5 if mode == "mapping" else 0.2)
        if mode == "mapping":
            self.mapping_rate = speed
        else:
            self.matching_rate = speed
        row.addWidget(speed)
        row.addWidget(self.button("載入 Bag（暫停）", lambda _checked=False, m=mode: self.start_bag(m), accent=True))
        row.addWidget(self.button("播放 / 暫停", self.toggle_bag))
        row.addWidget(self.button("停止播放", lambda: self.stop_role("bag"), danger=True))
        box.addLayout(row)
        return group

    def build_output_tab(self):
        content = QWidget()
        v = QVBoxLayout(content)
        group, l = self.pane("定位 / 建圖軌跡 CSV", "建圖記錄 /current_pose；定位記錄 /ndt_pose 與 /ndt_stat。請先開始記錄，再播放 bag，才能存到完整軌跡。")
        row = QHBoxLayout()
        row.addWidget(self.button("開始錄製 CSV", self.start_capture, accent=True))
        row.addWidget(self.button("停止並整理 CSV", self.stop_capture))
        row.addWidget(self.button("重新轉換 CSV", self.reconvert_last))
        row.addStretch()
        l.addLayout(row)
        self.csv_info = QLabel("尚未開始記錄")
        self.csv_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.csv_info.setWordWrap(True)
        l.addWidget(self.csv_info)
        v.addWidget(group)
        status, l = self.pane("驗證重點", "以下項目能讓學生知道輸出檔案的意義，不等同於定位精度的完整驗證。")
        for txt in (
                "✓ PCD 檔案存在，且在 RViz 可顯示",
                "✓ /ndt_pose 持續發布位姿（不是只發布一筆）",
                "✓ /ndt_stat 可檢查 score、iteration、exe_time",
                "△ 比較運算時間與原始 VLP-16 約 10 Hz 的資料頻率",
                "△ 只有同一份 bag 的自我比對，不可視為獨立的定位準確率評估",
                "△ 軌跡 CSV 是估計路徑，不是可直接給 Hunter 行駛的安全導航路徑",
        ):
            label = QLabel(txt)
            label.setWordWrap(True)
            l.addWidget(label)
        v.addWidget(status)
        row = QHBoxLayout()
        row.addWidget(self.button("開啟軌跡資料夾", self.open_trajectory_folder))
        row.addWidget(self.button("檢查所有 ROS Topic", self.list_topics))
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        return self.scroll_widget(content)

    def build_navigation_tab(self):
        """Waypoint generation and NO-MOTOR Pure Pursuit testing."""
        content = QWidget()
        v = QVBoxLayout(content)
        generation, box = self.pane(
            "① NDT 軌跡 → Autoware Waypoint v3",
            "先在「04 路徑與輸出」錄下完整的 NDT CSV；再從這裡產生 Waypoint。"
            "轉換器會檢查定位跳點，不會覆寫已有路徑。",
        )
        form = QFormLayout()
        self.nav_input, widget = self.field_with_browse(
            "~/autoware.ai/trajectory/ndt_matching_20261117_222744.csv")
        form.addRow("NDT 軌跡 CSV", widget)
        self.nav_output, widget = self.field_with_browse(
            "~/autoware.ai/trajectory/vlp16_waypoints_01.csv", False, False)
        form.addRow("Waypoint CSV", widget)
        box.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(self.button("使用最新 NDT CSV", lambda: self.suggest_nav_input(True)))
        row.addWidget(QLabel("取樣間距 (m)"))
        self.nav_spacing = QDoubleSpinBox()
        self.nav_spacing.setRange(0.1, 3.0)
        self.nav_spacing.setDecimals(2)
        self.nav_spacing.setSingleStep(0.1)
        self.nav_spacing.setValue(0.5)
        row.addWidget(self.nav_spacing)
        row.addWidget(QLabel("速度 (km/h)"))
        self.nav_speed = QDoubleSpinBox()
        self.nav_speed.setRange(0.1, 5.0)
        self.nav_speed.setDecimals(1)
        self.nav_speed.setSingleStep(0.1)
        self.nav_speed.setValue(2.0)
        row.addWidget(self.nav_speed)
        row.addStretch()
        box.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("最大跳點 (m)"))
        self.nav_max_jump = QDoubleSpinBox()
        self.nav_max_jump.setRange(0.1, 10.0)
        self.nav_max_jump.setDecimals(2)
        self.nav_max_jump.setValue(1.5)
        row.addWidget(self.nav_max_jump)
        row.addWidget(self.button("產生 Waypoint CSV", self.convert_nav_waypoints, accent=True))
        row.addWidget(self.button("檢查 Waypoint CSV", self.check_nav_waypoints))
        row.addStretch()
        box.addLayout(row)
        self.nav_info = QLabel("尚未檢查 Waypoint CSV")
        self.nav_info.setWordWrap(True)
        self.nav_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.nav_info)
        v.addWidget(generation)

        runtime, box = self.pane(
            "② 離線 ROS 導航節點",
            "需要先啟動「03 NDT 定位」；載入路徑後，啟動 Pure Pursuit / Twist Filter，"
            "再播放 Bag。僅生成 /offline_nav/* 計算結果，沒有 CAN／馬達驅動。"
            "這裡的 Waypoint 是預先記錄的固定路線，尚不具備避障重新規劃。",
        )
        row = QHBoxLayout()
        row.addWidget(self.button("載入 Waypoint", self.load_nav_waypoints, accent=True))
        row.addWidget(self.button("啟動 Pure Pursuit + Filter", self.start_nav_controller, accent=True))
        row.addWidget(self.button("停止導航測試", self.stop_nav_test, danger=True))
        row.addStretch()
        box.addLayout(row)
        config = QHBoxLayout()
        config.addWidget(QLabel("Lookahead Ratio"))
        self.nav_lookahead_ratio = QDoubleSpinBox()
        self.nav_lookahead_ratio.setRange(0.1, 20.0)
        self.nav_lookahead_ratio.setValue(2.0)
        self.nav_lookahead_ratio.setSingleStep(0.1)
        config.addWidget(self.nav_lookahead_ratio)
        config.addWidget(QLabel("Min Lookahead (m)"))
        self.nav_min_lookahead = QDoubleSpinBox()
        self.nav_min_lookahead.setRange(0.1, 30.0)
        self.nav_min_lookahead.setValue(1.5)
        self.nav_min_lookahead.setSingleStep(0.1)
        config.addWidget(self.nav_min_lookahead)
        config.addWidget(self.button("套用追蹤參數", self.publish_nav_config))
        config.addStretch()
        box.addLayout(config)
        row = QHBoxLayout()
        row.addWidget(self.button("檢查導航 Topics", self.check_nav_topics))
        row.addWidget(self.button("讀取一筆 Twist 指令", self.sample_nav_twist))
        row.addWidget(self.button("開啟導航 RViz", self.open_nav_rviz, accent=True))
        row.addStretch()
        box.addLayout(row)
        self.nav_ros_info = QLabel("尚未啟動離線導航。先載入 Waypoint，再啟動追蹤節點。")
        self.nav_ros_info.setWordWrap(True)
        self.nav_ros_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.nav_ros_info)
        v.addWidget(runtime)
        caution, box = self.pane("③ 驗證重點", "先完成離線命令鏈路測試，再確認 Hunter 車型與 CAN 驅動。")
        for item in (
                "✓ /based/lane_waypoints_raw：waypoint_loader 有輸出路徑",
                "✓ /offline_nav/final_waypoints：離線橋接已接收路徑",
                "✓ /offline_nav/current_pose：NDT /ndt_pose 有持續更新",
                "✓ /offline_nav/twist_raw：Pure Pursuit 有產生速度／轉向指令",
                "△ /offline_nav/twist_cmd：Twist Filter 輸出（確認濾波器參數）",
                "△ 尚未做障礙物偵測、避障、實車 CAN 速度限制與急停驗證",
        ):
            lbl = QLabel(item)
            lbl.setWordWrap(True)
            box.addWidget(lbl)
        v.addWidget(caution)
        v.addStretch()
        return self.scroll_widget(content)

    # ----- Configuration ---------------------------------------------------
    def path_value(self, line):
        return os.path.abspath(linux_path(line.text()))

    def workspace_path(self):
        return self.path_value(self.workspace)

    def extrinsics(self):
        return {k: float(w.value()) for k, w in self.extra_fields.items()}

    def load_settings(self):
        for key, widget in (("workspace", self.workspace), ("bag", self.bag_path),
                            ("map", self.map_path), ("trajectory", self.csv_folder)):
            value = self.settings.value(key)
            if value:
                widget.setText(value)
        for key, widget in self.extra_fields.items():
            try:
                widget.setValue(float(self.settings.value("tf_" + key, 0.0)))
            except (ValueError, TypeError):
                pass
        for mode, fields in self.ndt_fields.items():
            for name, widget in fields.items():
                value = self.settings.value("ndt_{}_{}".format(mode, name))
                if value is None:
                    continue
                try:
                    widget.setValue(float(value))
                except (ValueError, TypeError):
                    pass
        for key, field in (("nav_input", self.nav_input), ("nav_output", self.nav_output)):
            value = self.settings.value(key)
            if value:
                field.setText(value)
        for key, field in (("nav_spacing", self.nav_spacing),
                           ("nav_speed", self.nav_speed),
                           ("nav_max_jump", self.nav_max_jump),
                           ("nav_lookahead_ratio", self.nav_lookahead_ratio),
                           ("nav_min_lookahead", self.nav_min_lookahead)):
            try:
                value = self.settings.value(key)
                if value is not None:
                    field.setValue(float(value))
            except (ValueError, TypeError):
                pass

    def save_settings(self):
        for key, widget in (("workspace", self.workspace), ("bag", self.bag_path),
                            ("map", self.map_path), ("trajectory", self.csv_folder)):
            self.settings.setValue(key, widget.text())
        for key, widget in self.extra_fields.items():
            self.settings.setValue("tf_" + key, widget.value())
        for mode, fields in self.ndt_fields.items():
            for name, widget in fields.items():
                self.settings.setValue("ndt_{}_{}".format(mode, name), widget.value())
        for key, field in (("nav_input", self.nav_input), ("nav_output", self.nav_output)):
            self.settings.setValue(key, field.text())
        for key, field in (("nav_spacing", self.nav_spacing),
                           ("nav_speed", self.nav_speed),
                           ("nav_max_jump", self.nav_max_jump),
                           ("nav_lookahead_ratio", self.nav_lookahead_ratio),
                           ("nav_min_lookahead", self.nav_min_lookahead)):
            self.settings.setValue(key, field.value())
        self.settings.sync()
        self.message("設定已儲存。")

    def message(self, msg, origin="GUI"):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.logs.append("[{}] [{}] {}".format(stamp, origin, msg.replace("\x00", "")))

    def fail(self, message):
        self.message(message, "錯誤")
        QMessageBox.warning(self, "操作未完成", message)

    def validate_workspace(self):
        workspace = self.workspace_path()
        if not os.path.exists(os.path.join(workspace, "install", "setup.bash")):
            self.fail("找不到 {}。請確認 Autoware 工作空間已成功編譯。".format(os.path.join(workspace, "install", "setup.bash")))
            return False
        return True

    def check_environment(self):
        if not self.validate_workspace():
            return
        self.message("工作空間：{}".format(self.workspace_path()))
        for title, path in (("ROS bag", self.path_value(self.bag_path)), ("PCD 地圖", self.path_value(self.map_path))):
            self.message("{}：{} ({})".format(title, path, "存在" if os.path.isfile(path) else "尚未建立"))
        out = self.run_sync(["rosversion", "-d"], quiet=True)
        if out is not None:
            self.message("ROS distro: " + out.strip())
        self.save_settings()

    # ----- ROS commands & subprocess handling ----------------------------
    def command(self, args, overlay=True):
        return ["bash", "-lc", shell_command(self.workspace_path(), args, overlay)]

    def run_sync(self, args, quiet=False, timeout=8, overlay=True):
        try:
            result = subprocess.run(self.command(args, overlay), stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=timeout,
                                    universal_newlines=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            if not quiet:
                self.message(str(exc), "ROS")
            return None
        if result.returncode != 0:
            if not quiet:
                self.message("{} → {}".format(" ".join(args), result.stdout.strip()), "ROS")
            return None
        return result.stdout

    def spawn(self, role, args, use_pty=False, stdout_file=None, overlay=True):
        if self.alive(role):
            self.message("{} 已在執行。".format(role))
            return self.processes[role]
        out_file, pty_master, pty_slave = None, None, None
        try:
            if stdout_file is not None:
                out_file = open(stdout_file, "w", encoding="utf-8")
                proc = subprocess.Popen(self.command(args, overlay), stdout=out_file,
                                        stderr=subprocess.PIPE, start_new_session=True)
                stream = proc.stderr
            elif use_pty:
                pty_master, pty_slave = pty.openpty()
                proc = subprocess.Popen(self.command(args, overlay), stdin=pty_slave,
                                        stdout=pty_slave, stderr=pty_slave, start_new_session=True)
                os.close(pty_slave)
                pty_slave = None
                stream = pty_master
            else:
                proc = subprocess.Popen(self.command(args, overlay), stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, start_new_session=True)
                stream = proc.stdout
            if isinstance(stream, int):
                os.set_blocking(stream, False)
            else:
                os.set_blocking(stream.fileno(), False)
            managed = OwnedProcess(role, proc, stream=stream, stdin_pty=pty_master, output_file=out_file)
            self.processes[role] = managed
            self.message("啟動 {}：{}".format(role, " ".join(args)))
            self.update_status()
            return managed
        except OSError as exc:
            if out_file:
                out_file.close()
            if pty_master is not None:
                os.close(pty_master)
            if pty_slave is not None:
                os.close(pty_slave)
            self.fail("無法啟動 {}：{}".format(role, exc))
            return None

    def alive(self, role):
        return role in self.processes and self.processes[role].alive()

    def stop_role(self, role):
        if role in self.processes:
            self.processes[role].stop()
            self.message("要求停止 {}。".format(role))
        if role == "bag":
            self.bag_paused = False
        self.update_status()

    def stop_mode(self, mode):
        if mode == "matching":
            self.stop_nav_test()
        if self.alive("bag"):
            self.stop_role("bag")
        if self.alive("capture_pose") or self.alive("capture_stat"):
            self.stop_capture()
        self.stop_role(mode)
        self.stop_role("config_" + mode)
        self.active_ndt_configs.pop(mode, None)
        self.ndt_config_ready.discard(mode)
        if mode == "matching":
            self.stop_role("map_publisher")
            self.stop_role("set_initial_pose")

    def stop_all(self):
        for role in ("nav_twist_sample", "nav_config", "nav_filter_config",
                     "nav_rviz", "nav_controller", "nav_loader", "nav_bridge",
                     "capture_pose", "capture_stat", "bag", "config_mapping", "config_matching",
                     "set_initial_pose", "save_map",
                     "mapping", "matching", "map_publisher", "tf", "rviz", "core"):
            self.stop_role(role)
        self.mode = None
        self.active_ndt_configs.clear()
        self.ndt_config_ready.clear()
        self.update_status()

    def poll_processes(self):
        for role, obj in list(self.processes.items()):
            if obj.stream is not None:
                try:
                    fd = obj.stream if isinstance(obj.stream, int) else obj.stream.fileno()
                    if select.select([fd], [], [], 0)[0]:
                        data = os.read(fd, 10000).decode("utf-8", "replace")
                        if data:
                            if role == "bag":
                                obj.bag_status_buffer = (obj.bag_status_buffer + data)[-2048:]
                                progress = parse_bag_progress(obj.bag_status_buffer)
                                if progress is not None:
                                    self.last_bag_progress = progress
                                    self.show_bag_progress(progress)
                            normalized = data.replace("\r", "\n").strip()
                            if normalized:
                                lines = compact_ros_lines(
                                    role, normalized.splitlines(), self.verbose_logs.isChecked()
                                )
                                for line in lines:
                                    self.message(line[:900], role)
                except (OSError, ValueError):
                    pass
            if obj.alive():
                continue
            rc = obj.proc.returncode
            obj.close_files()
            self.processes.pop(role, None)
            if not obj.stopping:
                self.message("{} 已結束，exit code={}".format(role, rc), "程序")
                if role.startswith("config_"):
                    mode = role[len("config_"):]
                    if rc == 0 and mode in self.active_ndt_configs and self.alive(mode):
                        self.ndt_config_ready.add(mode)
                        self.message("{} 的 NDT 參數發布程序已完成。可開始播放 Bag。".format(mode), "參數")
                        if self.ndt_parameter_values(mode) == self.active_ndt_configs.get(mode):
                            self.ndt_hints[mode].setText("已送出本次啟動的 NDT 參數；修改數值後需重新啟動節點。")
                        else:
                            self.mark_ndt_pending(mode)
                    elif rc != 0 and mode in self.active_ndt_configs:
                        self.message("{} 的參數發布失敗。請查看 ROS 輸出並重新啟動節點。".format(mode), "警告")
            if role == "bag":
                self.bag_paused = False
                self.bag_started = False
                if self.last_bag_progress:
                    previous = self.last_bag_progress
                    state = "播放完成" if rc == 0 else "已停止"
                    self.bag_time_label.setText(
                        "Bag：{}  Duration: {:.2f} / {:.2f} s".format(
                            state, previous["elapsed"], previous["duration"]
                        )
                    )
                else:
                    self.bag_time_label.setText("Bag：播放完成" if rc == 0 else "Bag：已停止")
            if role in ("capture_pose", "capture_stat") and self.active_capture:
                if not self.alive("capture_pose") and not self.alive("capture_stat"):
                    self.finalize_capture()
            self.update_status()

    def badge(self, name, active, extra=""):
        label, title = self.badges[name]
        color = COLOR_OK if active else COLOR_OFF
        label.setText(title + ("  ● " + (extra or "運作中") if active else "  ● 未啟動"))
        label.setStyleSheet("color:{}; font-weight:600; padding:3px".format(color))

    def show_bag_progress(self, progress):
        total = progress["duration"]
        elapsed = progress["elapsed"]
        percent = max(0.0, min(100.0, 100.0 * elapsed / total)) if total > 0 else 0.0
        state = "[PAUSED]" if progress["paused"] else "[RUNNING]"
        self.bag_time_label.setText(
            "{}  Bag Time: {:.2f}   Duration: {:.2f} / {:.2f} s   ({:.1f}%)".format(
                state, progress["bag_time"], elapsed, total, percent
            )
        )

    def update_status(self):
        self.badge("core", self.alive("core") or self.is_master_up(), "已連線")
        self.badge("tf", self.alive("tf"))
        self.badge("mapping", self.alive("mapping"))
        self.badge("matching", self.alive("matching"))
        self.badge("bag", self.alive("bag"), "暫停" if self.bag_paused else "播放")
        self.badge("csv", self.alive("capture_pose"), "記錄中")
        self.badge("nav", self.alive("nav_bridge") or self.alive("nav_controller"),
                   "追蹤中" if self.alive("nav_controller") else "已載路徑")
        label = {None:"尚未選擇", "mapping":"NDT Mapping", "matching":"NDT Matching"}[self.mode]
        self.workflow_label.setText("目前模式：" + label)

    def is_master_up(self):
        # Called occasionally; direct XML-RPC avoids blocking on ROS CLI startup.
        try:
            from xmlrpc.client import ServerProxy
            host = os.environ.get("ROS_MASTER_URI", "http://localhost:11311")
            import socket
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(0.35)
            try:
                return ServerProxy(host, allow_none=True).getPid("/student_gui")[0] == 1
            finally:
                socket.setdefaulttimeout(old_timeout)
        except Exception:
            return False

    def ensure_core_only(self):
        if not self.validate_workspace():
            return
        if self.is_master_up():
            self.message("已偵測到 ROS Master；將重用它，不會關閉外部 ROS Master。")
            return
        self.spawn("core", ["roscore"], overlay=False)

    def wait_for_core(self):
        if self.is_master_up():
            requested = self.pending_mode
            self.pending_mode = None
            if requested:
                self.continue_prepare(requested)
            return
        if time.monotonic() > self.core_deadline:
            self.pending_mode = None
            self.fail("等待 ROS Master 逾時。請查看下方 roscore 記錄。")
            return
        QTimer.singleShot(500, self.wait_for_core)

    # ----- Mapping & matching workflows -----------------------------------
    def prepare_mode(self, mode):
        if self.alive("bag"):
            self.fail("請先停止正在播放的 bag，再切換工作流程。")
            return
        other = "matching" if mode == "mapping" else "mapping"
        if self.alive(other):
            self.fail("請先按『停止{}節點』，避免兩種模式同時執行。".format("定位" if other == "matching" else "建圖"))
            return
        if self.alive(mode):
            self.message("{} 已在執行，無需重複啟動。".format(mode))
            return
        if not self.validate_workspace():
            return
        if not os.path.isfile(self.path_value(self.bag_path)):
            self.fail("找不到 bag：{}".format(self.path_value(self.bag_path)))
            return
        if mode == "matching" and not os.path.isfile(self.path_value(self.map_path)):
            self.fail("找不到 PCD 地圖：{}".format(self.path_value(self.map_path)))
            return
        try:
            config = self.ndt_parameter_values(mode)
        except (ValueError, TypeError) as exc:
            self.fail("請先修正 NDT 參數：{}".format(exc))
            return
        # Freeze this run's values: editing the controls mid-run only affects
        # the next node launch, including matching's initial-pose re-publish.
        self.active_ndt_configs[mode] = config
        self.ndt_config_ready.discard(mode)
        self.save_settings()
        if not self.is_master_up():
            self.pending_mode = mode
            self.core_deadline = time.monotonic() + 20.0
            self.ensure_core_only()
            QTimer.singleShot(500, self.wait_for_core)
            return
        self.continue_prepare(mode)

    def continue_prepare(self, mode):
        nodes = self.run_sync(["rosnode", "list"], quiet=True) or ""
        for conflict in ("/ndt_mapping", "/ndt_matching"):
            if conflict in nodes.splitlines() and not self.alive(conflict[1:]):
                self.fail("ROS Master 上已有外部節點 {}。請先停止手動啟動的節點，避免名稱衝突。".format(conflict))
                return
        params = [("/use_sim_time", "true"), ("/localizer", "velodyne")]
        for key, value in self.extrinsics().items():
            params.append(("/tf_" + key, fmt_number(value)))
        for param, value in params:
            if self.run_sync(["rosparam", "set", param, value]) is None:
                self.fail("無法設定 {}。請確認 ROS Master 已啟動。".format(param))
                return
        self.message("ROS 使用模擬時間；外參已設定。")
        if self.alive("tf"):
            self.stop_role("tf")
            # Do not start a new publisher until the old owned node has exited.
            QTimer.singleShot(800, lambda: self.launch_mode_after_tf(mode))
        else:
            self.launch_mode_after_tf(mode)

    def launch_mode_after_tf(self, mode):
        if self.alive("tf"):
            QTimer.singleShot(500, lambda: self.launch_mode_after_tf(mode))
            return
        self.spawn("tf", tf_arguments(self.extrinsics()))
        self.mode = mode
        if mode == "mapping":
            if self.alive("map_publisher"):
                self.stop_role("map_publisher")
            self.spawn("mapping", ["roslaunch", "lidar_localizer", "ndt_mapping.launch",
                                   "method_type:=0", "use_odom:=false", "use_imu:=false"])
            self.tabs.setCurrentIndex(1)
        else:
            self.spawn("map_publisher", ["rosrun", "pcl_ros", "pcd_to_pointcloud",
                                         self.path_value(self.map_path), "0.5",
                                         "_frame_id:=map", "/cloud_pcd:=/points_map"])
            self.spawn("matching", ["roslaunch", "lidar_localizer", "ndt_matching.launch",
                                    "method_type:=0", "use_gnss:=false", "use_odom:=false", "use_imu:=false"])
            self.tabs.setCurrentIndex(2)
            self.message("初始位姿會在 bag 第一次開始播放、收到 /clock 後自動發布。")
        QTimer.singleShot(3500, lambda: self.confirm_node_started(mode))
        self.message("{} 環境已提出啟動要求；請查看狀態及紀錄。".format(mode))

    def confirm_node_started(self, mode, attempts=0):
        if (self.mode != mode or not self.alive(mode)
                or self.processes[mode].stopping or mode not in self.active_ndt_configs):
            return
        output = self.run_sync(["rosnode", "list"], quiet=True, timeout=5) or ""
        name = "/ndt_mapping" if mode == "mapping" else "/ndt_matching"
        topic = "/config/ndt_mapping" if mode == "mapping" else "/config/ndt"
        info = self.run_sync(["rostopic", "info", topic], quiet=True, timeout=5) or ""
        subscribers = info.split("Subscribers:", 1)[-1] if "Subscribers:" in info else ""
        if name in output.splitlines() and name in subscribers:
            self.message("ROS 節點 {} 與參數訂閱端已就緒。".format(name), "檢查")
            self.publish_startup_ndt_config(mode)
        elif attempts < 12:
            QTimer.singleShot(1000, lambda: self.confirm_node_started(mode, attempts + 1))
        else:
            self.message("未偵測到 {} 的 {} 訂閱端，因此未發送參數。"
                         "請檢查節點輸出與 ROS 連線後重新啟動。".format(name, topic), "警告")

    def publish_startup_ndt_config(self, mode):
        if mode not in self.active_ndt_configs or not self.alive(mode):
            return
        config = self.active_ndt_configs[mode]
        obj = self.spawn("config_" + mode, ndt_config_command(mode, config))
        if obj is not None:
            self.ndt_hints[mode].setText("正在發送本次啟動的 NDT 參數…")
            self.message("{} 本次啟動參數：{}".format(mode, json.dumps(config, sort_keys=True)), "參數")

    def publish_initial_pose(self):
        if not self.alive("matching"):
            self.message("NDT Matching 尚未啟動，無法發布初始位姿。")
            return
        # Do not send currently edited-but-pending values during playback.
        config = self.active_ndt_configs.get("matching", match_config())
        self.spawn("set_initial_pose", ["rostopic", "pub", "-1", "/config/ndt",
                                        NDT_CONFIG_TYPE, json.dumps(config)])
        self.message("已要求將定位起點設為地圖原點 (0,0,0,0,0,0)。")

    def export_pcd(self):
        if not self.alive("mapping"):
            self.fail("必須先啟動 NDT Mapping，且至少處理一些點雲後才能匯出 PCD。")
            return
        target = self.path_value(self.map_path)
        if os.path.exists(target):
            if QMessageBox.question(self, "覆寫地圖？", "地圖已存在：\n{}\n\n確定覆寫？".format(target),
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        os.makedirs(os.path.dirname(target), exist_ok=True)
        payload = {"header":{"frame_id":"map"}, "filename":target,
                   "filter_res":float(self.pcd_resolution.value())}
        self.spawn("save_map", ["rostopic", "pub", "-1", "/config/ndt_mapping_output",
                                MAP_OUTPUT_TYPE, json.dumps(payload)])
        self.message("正在要求 NDT Mapping 儲存 PCD；完成後請查看檔案大小。")

    # ----- Bag player using a PTY so Space really reaches rosbag ----------
    def start_bag(self, requested_mode):
        if self.mode != requested_mode or not self.alive(requested_mode):
            self.fail("請先啟動此頁面的 {} 節點。".format(requested_mode))
            return
        if self.alive("bag"):
            self.message("bag 已經載入。請使用『播放 / 暫停』。")
            return
        if requested_mode not in self.ndt_config_ready:
            self.fail("NDT 參數尚未確認發布完成。請等候下方顯示『參數發布程序已完成』後再載入 Bag。")
            return
        rate = self.mapping_rate.value() if requested_mode == "mapping" else self.matching_rate.value()
        args = ["rosbag", "play", "--clock", "--pause", "-r", fmt_number(rate), self.path_value(self.bag_path)]
        if requested_mode == "matching":
            args.append("/points_raw:=/filtered_points")
        obj = self.spawn("bag", args, use_pty=True)
        self.bag_paused = obj is not None
        self.bag_started = obj is not None
        self.pose_initialized_for_bag = False
        self.last_bag_progress = None
        if obj is not None:
            self.bag_time_label.setText("[PAUSED]  Bag：已載入，等待播放  ({}×)".format(fmt_number(rate)))
        self.message("bag 載入後預設暫停。按『播放 / 暫停』會送出 Space。")
        self.update_status()

    def toggle_bag(self):
        obj = self.processes.get("bag")
        if not obj or not obj.alive() or obj.stdin_pty is None:
            self.fail("尚未載入 bag。先按『載入 Bag（暫停）』。")
            return
        try:
            os.write(obj.stdin_pty, b" ")
            self.bag_paused = not self.bag_paused
            self.message("bag 已要求{}。".format("暫停" if self.bag_paused else "繼續播放"))
            if (not self.bag_paused and self.mode == "matching"
                    and not self.pose_initialized_for_bag):
                self.pose_initialized_for_bag = True
                QTimer.singleShot(500, self.publish_initial_pose)
            self.update_status()
        except OSError as exc:
            self.fail("無法控制 rosbag 的 PTY：{}".format(exc))

    # ----- Trajectory recording -------------------------------------------
    def start_capture(self):
        if self.mode not in ("mapping", "matching") or not self.alive(self.mode):
            self.fail("請先在建圖或定位頁籤啟動對應節點。")
            return
        if self.alive("capture_pose"):
            self.message("CSV 已經在記錄中。")
            return
        folder = self.path_value(self.csv_folder)
        os.makedirs(folder, exist_ok=True)
        sid = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = "ndt_matching" if self.mode == "matching" else "ndt_mapping"
        raw = os.path.join(folder, "{}_{}_raw.csv".format(stem, sid))
        clean = os.path.join(folder, "{}_{}.csv".format(stem, sid))
        stats = os.path.join(folder, "{}_{}_stat.csv".format(stem, sid)) if self.mode == "matching" else None
        topic = "/ndt_pose" if self.mode == "matching" else "/current_pose"
        self.active_capture = {"raw":raw, "clean":clean, "stat":stats}
        self.last_capture = dict(self.active_capture)
        obj = self.spawn("capture_pose", ["rostopic", "echo", "-p", topic], stdout_file=raw)
        if obj is None:
            self.active_capture = None
            return
        if stats:
            self.spawn("capture_stat", ["rostopic", "echo", "-p", "/ndt_stat"], stdout_file=stats)
        self.csv_info.setText("記錄中：\n{}\n{}".format(raw, stats or ""))
        self.message("CSV 記錄已啟動。注意：請在錄製開始之後播放 bag。")

    def stop_capture(self):
        if not self.alive("capture_pose") and not self.alive("capture_stat"):
            self.message("目前沒有正在執行的 CSV 記錄。")
            return
        self.stop_role("capture_pose")
        self.stop_role("capture_stat")
        self.message("等待 CSV 記錄程序結束，再自動轉換為 time/XYZ/RPY。")

    def finalize_capture(self):
        capture = self.active_capture
        self.active_capture = None
        if not capture or not os.path.isfile(capture["raw"]):
            return
        try:
            count = convert_pose_csv(capture["raw"], capture["clean"])
        except (OSError, ValueError) as exc:
            self.message("CSV 轉換未完成：{}；原始檔仍保留。".format(exc), "CSV")
            return
        self.csv_info.setText("已輸出 {} 筆軌跡：\n{}\n原始：{}\n統計：{}".format(
            count, capture["clean"], capture["raw"], capture.get("stat") or "無"))
        self.message("CSV 已整理成 {} 筆：{}".format(count, capture["clean"]), "CSV")
        if self.mode == "matching" and count >= 3:
            self.nav_input.setText(capture["clean"])

    def reconvert_last(self):
        if not self.last_capture:
            self.fail("這次操作還沒有 CSV。請先錄製定位／建圖資料。")
            return
        try:
            count = convert_pose_csv(self.last_capture["raw"], self.last_capture["clean"])
        except (OSError, ValueError) as exc:
            self.fail("轉換失敗：{}".format(exc))
            return
        self.message("重新轉換完成：{} 筆 → {}".format(count, self.last_capture["clean"]))

    # ----- Offline Waypoint / Pure Pursuit demonstration -----------------
    def suggest_nav_input(self, force=False):
        if not force and self.settings.value("nav_input") and os.path.isfile(
                self.path_value(self.nav_input)):
            return
        folder = self.path_value(self.csv_folder)
        candidates = [path for path in glob.glob(os.path.join(folder, "ndt_matching_*.csv"))
                      if not path.endswith(("_raw.csv", "_stat.csv"))]
        if candidates:
            chosen = max(candidates, key=os.path.getmtime)
            self.nav_input.setText(chosen)
            if force:
                self.message("已選擇最新定位軌跡：{}".format(chosen), "Waypoint")
        elif force:
            self.fail("找不到 NDT Matching 軌跡 CSV。請先完成定位軌跡記錄。")

    def convert_nav_waypoints(self):
        source, target = self.path_value(self.nav_input), self.path_value(self.nav_output)
        script = os.path.join(APP_ROOT, "convert_ndt_to_waypoints.py")
        if not os.path.isfile(script):
            self.fail("找不到 Waypoint 轉換器：{}".format(script))
            return
        if not os.path.isfile(source):
            self.fail("NDT 軌跡 CSV 不存在：{}".format(source))
            return
        if os.path.exists(target):
            self.fail("Waypoint 已存在，不會覆寫：\n{}\n請修改輸出檔名（例如 _02.csv），或直接按『檢查 Waypoint CSV』。".format(target))
            return
        command = ["python3", script, "--input", source, "--output", target,
                   "--spacing-m", fmt_number(self.nav_spacing.value()),
                   "--speed-kmh", fmt_number(self.nav_speed.value()),
                   "--max-jump-m", fmt_number(self.nav_max_jump.value())]
        try:
            completed = subprocess.run(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, timeout=30,
                                       universal_newlines=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.fail("Waypoint 轉換器無法執行：{}".format(exc))
            return
        for line in completed.stdout.splitlines():
            self.message(line, "Waypoint")
        if completed.returncode != 0:
            self.fail("Waypoint 轉換失敗。請查看下方錯誤訊息。")
            return
        self.check_nav_waypoints()
        self.save_settings()

    def check_nav_waypoints(self):
        path = self.path_value(self.nav_output)
        try:
            count, length, max_speed = inspect_waypoint_csv(path)
        except (OSError, ValueError) as exc:
            self.nav_info.setText("Waypoint 檢查未通過：{}".format(exc))
            self.fail("Waypoint 檢查未通過：{}".format(exc))
            return False
        self.nav_info.setText("檢查通過：{}\n{} 點，長度約 {:.2f} m，最高設定速度 {:.2f} km/h。"
                              .format(path, count, length, max_speed))
        self.message("Waypoint 格式檢查通過：{} 點 / {:.2f} m".format(count, length),
                     "Waypoint")
        return True

    def load_nav_waypoints(self):
        if not self.is_master_up():
            self.fail("請先啟動 ROS Master 與 NDT Matching，再載入 Waypoint。")
            return
        if self.alive("nav_bridge") or self.alive("nav_loader") or self.alive("nav_controller"):
            self.fail("離線導航節點已經啟動。若要換路線，請先按『停止導航測試』。")
            return
        if not self.validate_workspace() or not self.check_nav_waypoints():
            return
        for pkg in ("waypoint_maker", "pure_pursuit", "twist_filter"):
            if self.run_sync(["rospack", "find", pkg], quiet=True, timeout=5) is None:
                self.fail("ROS 套件 {} 尚不可用。請確認 colcon build 成功並已 source install/setup.bash。".format(pkg))
                return
        nodes = (self.run_sync(["rosnode", "list"], quiet=True, timeout=5) or "").splitlines()
        conflicts = ("/offline_nav_bridge", "/waypoint_loader",
                     "/offline_pure_pursuit", "/offline_twist_filter")
        if any(n in nodes for n in conflicts):
            self.fail("ROS Master 上存在同名的外部導航測試節點。請先停止外部程序。")
            return
        bridge_path = os.path.join(APP_ROOT, "offline_nav_bridge.py")
        if not os.path.isfile(bridge_path):
            self.fail("找不到離線橋接程式：{}".format(bridge_path))
            return
        self.save_settings()
        if self.spawn("nav_bridge", ["python2", bridge_path]) is None:
            return
        target = self.path_value(self.nav_output)
        self.nav_ros_info.setText("正在啟動離線橋接，稍後載入：{}".format(target))
        QTimer.singleShot(1200, lambda: self.launch_nav_loader(target))

    def launch_nav_loader(self, target):
        if not self.alive("nav_bridge") or not os.path.isfile(target):
            self.message("離線橋接未啟動或路徑檔案已移動，取消 waypoint_loader。", "警告")
            return
        obj = self.spawn("nav_loader", ["rosrun", "waypoint_maker", "waypoint_loader",
                                        "_multi_lane_csv:=" + target])
        if obj is not None:
            self.nav_ros_info.setText("已要求載入 {}\n等待 /based/lane_waypoints_raw。"
                                      .format(target))
            self.message("已啟動 Waypoint 載入；可按『檢查導航 Topics』確認路徑。", "Waypoint")

    def start_nav_controller(self):
        if not self.alive("nav_bridge"):
            self.fail("請先按『載入 Waypoint』，等待導航橋接啟動。")
            return
        if self.alive("nav_controller"):
            self.message("Pure Pursuit / Twist Filter 已在執行。", "Nav")
            return
        launch = os.path.join(APP_ROOT, "launch", "offline_pure_pursuit.launch")
        if not os.path.isfile(launch):
            self.fail("找不到離線控制 launch：{}".format(launch))
            return
        if self.spawn("nav_controller", ["roslaunch", launch]) is not None:
            self.nav_ros_info.setText(
                "Pure Pursuit / Twist Filter 啟動中。\n"
                "輸出僅在 /offline_nav/twist_raw 和 /offline_nav/twist_cmd。"
            )
            QTimer.singleShot(1800, self.publish_nav_config)

    def publish_nav_config(self):
        if not self.alive("nav_controller"):
            self.message("Pure Pursuit 尚未啟動，無法發送追蹤參數。", "Nav")
            return
        # ConfigWaypointFollower parameters use km/h, as do waypoint CSV files.
        payload = {
            "param_flag": 0,  # waypoint velocity mode
            "velocity": float(self.nav_speed.value()),
            "lookahead_distance": float(self.nav_min_lookahead.value()),
            "lookahead_ratio": float(self.nav_lookahead_ratio.value()),
            "minimum_lookahead_distance": float(self.nav_min_lookahead.value()),
        }
        self.spawn("nav_config", ["rostopic", "pub", "-1",
                                  "/offline_nav/config/waypoint_follower",
                                  "autoware_config_msgs/ConfigWaypointFollower", json.dumps(payload)])
        filter_payload = {"lateral_accel_limit": 1.0,
                          "lateral_jerk_limit": 5.0,
                          "lowpass_gain_linear_x": 0.0,
                          "lowpass_gain_angular_z": 0.0}
        self.spawn("nav_filter_config", ["rostopic", "pub", "-1",
                                         "/offline_nav/config/twist_filter",
                                         "autoware_config_msgs/ConfigTwistFilter",
                                         json.dumps(filter_payload)])
        self.message("已要求套用離線 Pure Pursuit 參數：{}".format(json.dumps(payload)), "Nav")
        self.message("已要求套用離線 Twist Filter 參數：{}".format(
            json.dumps(filter_payload)), "Nav")
        self.save_settings()

    def check_nav_topics(self):
        if not self.is_master_up():
            self.fail("目前沒有 ROS Master。")
            return
        found = self.run_sync(["rostopic", "list"], quiet=True, timeout=6)
        if found is None:
            self.fail("無法取得 ROS Topic。")
            return
        published = set(found.splitlines())
        targets = ("/based/lane_waypoints_raw", "/offline_nav/final_waypoints",
                   "/offline_nav/current_pose", "/offline_nav/current_velocity",
                   "/offline_nav/twist_raw", "/offline_nav/twist_cmd")
        result = ["{} {}".format("✓" if topic in published else "—", topic)
                  for topic in targets]
        self.nav_ros_info.setText("\n".join(result))
        for line in result:
            self.message(line, "Nav Topic")
        self.message("Topic 出現在清單上只代表已建立；要確認有資料，需播放 Bag 並檢查訊息頻率。", "Nav")

    def sample_nav_twist(self):
        if not self.alive("nav_controller"):
            self.fail("請先啟動 Pure Pursuit / Twist Filter，再開始播放 Bag。")
            return
        if self.alive("nav_twist_sample"):
            self.message("正在等待一筆 Twist 訊息；請繼續播放 Bag。", "Nav")
            return
        self.spawn("nav_twist_sample", ["rostopic", "echo", "-n", "1",
                                        "/offline_nav/twist_cmd"])
        self.message("正在等待 /offline_nav/twist_cmd 的一筆控制命令…", "Nav")

    def stop_nav_test(self):
        for role in ("nav_twist_sample", "nav_config", "nav_filter_config",
                     "nav_rviz", "nav_controller", "nav_loader", "nav_bridge"):
            if self.alive(role):
                self.stop_role(role)
        if hasattr(self, "nav_ros_info"):
            self.nav_ros_info.setText("已要求停止本面板的離線導航節點。")

    # ----- Other actions ---------------------------------------------------
    def open_rviz(self):
        if self.alive("rviz"):
            self.message("RViz 已由本面板啟動。")
            return
        basename = "matching.rviz" if self.mode == "matching" else "mapping.rviz"
        cfg = os.path.join(APP_ROOT, "rviz", basename)
        args = ["rviz", "-d", cfg] if os.path.isfile(cfg) else ["rviz"]
        self.spawn("rviz", args)

    def open_nav_rviz(self):
        """Launch the offline navigation display without changing mapping RViz."""
        if self.alive("nav_rviz"):
            self.message("導航 RViz 已經開啟。", "Nav")
            return
        cfg = os.path.join(APP_ROOT, "rviz", "navigation.rviz")
        if not os.path.isfile(cfg):
            self.fail("找不到導航 RViz 設定檔：{}".format(cfg))
            return
        if self.spawn("nav_rviz", ["rviz", "-d", cfg]) is not None:
            self.message("已開啟導航 RViz：地圖、完整 Waypoint 路徑、NDT Pose、Pure Pursuit 標記。",
                         "Nav")

    def list_topics(self):
        result = self.run_sync(["rostopic", "list"], quiet=True)
        if result is None:
            self.fail("目前讀取不到 ROS Topic。")
        else:
            self.message(result.strip() or "尚無 Topic", "Topics")

    def check_pose_topic(self):
        out = self.run_sync(["rostopic", "info", "/ndt_pose"], quiet=True)
        self.message((out or "無法取得 /ndt_pose 資訊").strip(), "NDT")

    def open_trajectory_folder(self):
        folder = self.path_value(self.csv_folder)
        os.makedirs(folder, exist_ok=True)
        # WSL's minimal Ubuntu image often has no xdg-open or Linux file manager.
        # Windows Explorer can open WSL files using the Windows path from wslpath.
        if shutil.which("explorer.exe") and shutil.which("wslpath"):
            try:
                win_path = subprocess.check_output(
                    ["wslpath", "-w", folder], universal_newlines=True, timeout=5
                ).strip()
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                self.message("WSL 路徑轉換失敗：{}".format(exc), "警告")
            else:
                self.spawn("folder", ["explorer.exe", win_path], overlay=False)
                return
        if shutil.which("xdg-open"):
            self.spawn("folder", ["xdg-open", folder], overlay=False)
            return
        self.fail("找不到檔案總管。請在 WSL 終端機執行：\ncd {}\nexplorer.exe .".format(folder))

    def closeEvent(self, event):
        running = [key for key, proc in self.processes.items() if proc.alive()]
        if running:
            result = QMessageBox.question(
                self, "離開教學面板", "目前有本面板啟動的程序：{}。\n離開將停止這些程序（不會停止外部 ROS Master）。確定離開？".format(", ".join(running)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if result != QMessageBox.Yes:
                event.ignore()
                return
        self.save_settings()
        self.stop_all()
        # Let child roslaunch/rosbag process groups exit before the GUI quits.
        # This also flushes open CSV files so that a clean CSV can be exported.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and any(p.alive() for p in self.processes.values()):
            time.sleep(0.05)
        for obj in self.processes.values():
            if obj.alive():
                try:
                    os.killpg(os.getpgid(obj.proc.pid), signal.SIGTERM)
                except OSError:
                    pass
            obj.close_files()
        self.processes.clear()
        if self.active_capture:
            self.finalize_capture()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Autoware Student GUI")
    window = StudentGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
