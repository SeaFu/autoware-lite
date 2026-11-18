#!/usr/bin/env python3
"""Pure-Python utilities for the Autoware.AI student panel.

This module deliberately does not import ROS or Qt.  It is testable on a
regular computer, while the GUI itself is intended to run inside ROS Melodic.
"""

import csv
import json
import math
import os
import re
import shlex


NDT_CONFIG_TYPE = "autoware_config_msgs/ConfigNDT"
MAPPING_CONFIG_TYPE = "autoware_config_msgs/ConfigNDTMapping"
MAP_OUTPUT_TYPE = "autoware_config_msgs/ConfigNDTMappingOutput"

_ROS_ERROR_RE = re.compile(
    r"\b(error|warning|warn|fatal|exception|failed|failure|abort|aborted|"
    r"not found|no such file|segmentation fault|cannot)\b", re.IGNORECASE,
)
_MAPPING_COUNT_RE = re.compile(r"\(Processed/Input\):\s*\((\d+)\s*/\s*(\d+)\)")
_BAG_PROGRESS_RE = re.compile(
    r"\[(RUNNING|PAUSED)\]\s+Bag Time:\s*([0-9.]+)\s+"
    r"Duration:\s*(-?[0-9.]+)\s*/\s*([0-9.]+)"
)


def parse_bag_progress(text):
    """Read the latest rosbag play time update (a carriage-return line).

    ROS1 `rosbag play` repeatedly prints `[RUNNING] Bag Time: ...
    Duration: ... / ...` with CR instead of a newline.
    """
    matches = list(_BAG_PROGRESS_RE.finditer(text))
    if not matches:
        return None
    state, bag_time, elapsed, duration = matches[-1].groups()
    return {
        "paused": state == "PAUSED",
        "bag_time": float(bag_time),
        "elapsed": float(elapsed),
        "duration": float(duration),
    }


def compact_ros_lines(role, lines, detailed=False):
    """Return readable GUI lines without streaming bag/NDT spam.

    Important errors are always visible. Detailed mode retains the latest
    seven lines from any process; normal mode collapses recurring NDT output.
    """
    cleaned = [line.strip() for line in lines if line.strip()]
    if role == "bag":
        # Time updates belong in the GUI's one-line progress label, regardless
        # of the detailed-output setting. Never append those updates to logs.
        cleaned = [
            line for line in cleaned
            if not (_BAG_PROGRESS_RE.search(line) or "Bag Time:" in line
                    or "Duration:" in line or "[RUNNING]" in line
                    or "[PAUSED]" in line)
        ]
        if detailed:
            return cleaned[-7:]
        return [line for line in cleaned if _ROS_ERROR_RE.search(line)][-3:]
    if detailed:
        return cleaned[-7:]
    if role == "mapping":
        result = []
        for line in cleaned:
            if _ROS_ERROR_RE.search(line):
                result.append(line)
                continue
            match = _MAPPING_COUNT_RE.search(line)
            if match:
                processed, total = (int(value) for value in match.groups())
                if processed == 1 or processed % 50 == 0:
                    result.append("建圖進度：已處理 {} / {} 筆點雲".format(processed, total))
        return result[-5:]
    return cleaned[-7:]


def linux_path(value):
    """Accept a WSL path or a Windows drive path copied from Explorer."""
    value = os.path.expanduser(value.strip().strip('"'))
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", value)
    if match:
        drive, suffix = match.groups()
        return "/mnt/{}/{}".format(drive.lower(), suffix.replace("\\", "/"))
    return value


def shell_command(workspace, arguments, needs_overlay=True):
    """Construct a shell command with safely quoted user paths and arguments."""
    base = "/opt/ros/melodic/setup.bash"
    overlay = os.path.join(linux_path(workspace), "install", "setup.bash")
    setup = "source {}".format(shlex.quote(base))
    if needs_overlay:
        setup += " && source {}".format(shlex.quote(overlay))
    return setup + " && exec " + " ".join(shlex.quote(str(x)) for x in arguments)


def fmt_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("外參必須是有限數值")
    return "{:.9g}".format(number)


def tf_arguments(extrinsics):
    """ROS1 tf CLI expects x y z YAW PITCH ROLL parent child period_ms."""
    return [
        "rosrun", "tf", "static_transform_publisher",
        fmt_number(extrinsics["x"]), fmt_number(extrinsics["y"]),
        fmt_number(extrinsics["z"]), fmt_number(extrinsics["yaw"]),
        fmt_number(extrinsics["pitch"]), fmt_number(extrinsics["roll"]),
        "base_link", "velodyne", "100",
    ]


def _ndt_overrides(config, overrides):
    """Validate editable NDT fields before publishing a ROS configuration."""
    if overrides:
        unknown = set(overrides) - set(config)
        if unknown:
            raise ValueError("未支援的 NDT 參數：{}".format(", ".join(sorted(unknown))))
        config.update(overrides)
    for name in ("resolution", "step_size", "trans_epsilon"):
        value = float(config[name])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("{} 必須大於 0".format(name))
        config[name] = value
    iterations = config["max_iterations"]
    if isinstance(iterations, bool) or int(iterations) != iterations or int(iterations) < 1:
        raise ValueError("max_iterations 必須是正整數")
    config["max_iterations"] = int(iterations)
    return config


def mapping_config(overrides=None):
    """Autoware.AI 1.14 ndt_mapping.cpp defaults and config message fields."""
    config = {
        "resolution": 1.0, "step_size": 0.1,
        "trans_epsilon": 0.01, "max_iterations": 30,
        "leaf_size": 2.0, "min_scan_range": 5.0,
        "max_scan_range": 200.0, "min_add_scan_shift": 1.0,
    }
    config = _ndt_overrides(config, overrides)
    for name in ("leaf_size", "max_scan_range"):
        value = float(config[name])
        if not math.isfinite(value) or value <= 0:
            raise ValueError("{} 必須大於 0".format(name))
        config[name] = value
    for name in ("min_scan_range", "min_add_scan_shift"):
        value = float(config[name])
        if not math.isfinite(value) or value < 0:
            raise ValueError("{} 不可為負值".format(name))
        config[name] = value
    if config["min_scan_range"] >= config["max_scan_range"]:
        raise ValueError("Min Scan Range 必須小於 Max Scan Range")
    return config


def match_config(overrides=None):
    """ConfigNDT with GNSS-free origin pose, plus editable NDT parameters."""
    config = {
        "init_pos_gnss": 0,
        "x": 0.0, "y": 0.0, "z": 0.0,
        "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
        "use_predict_pose": 0, "error_threshold": 0.1,
        "resolution": 1.0, "step_size": 0.1,
        "trans_epsilon": 0.01, "max_iterations": 30,
    }
    return _ndt_overrides(config, overrides)


def ndt_config_command(mode, config):
    """Produce the exact one-shot ROS topic publication for the selected mode."""
    if mode == "mapping":
        topic, msg_type = "/config/ndt_mapping", MAPPING_CONFIG_TYPE
        checked = mapping_config(config)
    elif mode == "matching":
        topic, msg_type = "/config/ndt", NDT_CONFIG_TYPE
        checked = match_config(config)
    else:
        raise ValueError("未知 NDT 模式：{}".format(mode))
    return ["rostopic", "pub", "-1", topic, msg_type, json.dumps(checked)]


def _find_field(fieldnames, suffix):
    matches = [f for f in fieldnames if f.strip().lstrip("%").endswith(suffix)]
    if len(matches) != 1:
        raise ValueError("找不到唯一的 ROS CSV 欄位：{}；實際欄位：{}".format(suffix, fieldnames))
    return matches[0]


def quaternion_rpy(x, y, z, w):
    norm = math.sqrt(x*x + y*y + z*z + w*w)
    if norm < 1e-12:
        raise ValueError("姿態四元數的長度為零")
    x, y, z, w = (v / norm for v in (x, y, z, w))
    roll = math.atan2(2*(w*x + y*z), 1 - 2*(x*x + y*y))
    pitch_arg = max(-1.0, min(1.0, 2*(w*y - z*x)))
    pitch = math.asin(pitch_arg)
    yaw = math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))
    return roll, pitch, yaw


def convert_pose_csv(raw_csv_path, clean_csv_path):
    """Convert `rostopic echo -p /ndt_pose` to time/XYZ/RPY for MATLAB.

    Returns number of successfully converted poses. Existing raw CSV is kept.
    """
    with open(raw_csv_path, newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        columns = reader.fieldnames or []
        if not columns:
            raise ValueError("原始 CSV 為空，請先播放 bag 並記錄 /ndt_pose")
        time_col = columns[0]
        names = {
            name: _find_field(columns, suffix)
            for name, suffix in (
                ("x", "pose.position.x"), ("y", "pose.position.y"),
                ("z", "pose.position.z"),
                ("qx", "pose.orientation.x"), ("qy", "pose.orientation.y"),
                ("qz", "pose.orientation.z"), ("qw", "pose.orientation.w"),
            )
        }
        count = 0
        initial = None
        with open(clean_csv_path, "w", newline="", encoding="utf-8") as dest:
            writer = csv.writer(dest)
            writer.writerow(["time_s", "ros_time_s", "x", "y", "z", "roll", "pitch", "yaw", "yaw_deg"])
            for row in reader:
                if not row or not row.get(time_col):
                    continue
                try:
                    t = float(row[time_col])
                    if t > 1e12:  # ROS1 plot format uses nanoseconds.
                        t /= 1e9
                    px, py, pz = (float(row[names[k]]) for k in ("x", "y", "z"))
                    quat = (float(row[names[k]]) for k in ("qx", "qy", "qz", "qw"))
                    roll, pitch, yaw = quaternion_rpy(*quat)
                except (ValueError, TypeError, KeyError):
                    continue
                if initial is None:
                    initial = t
                writer.writerow([
                    "{:.6f}".format(t - initial), "{:.9f}".format(t),
                    "{:.9f}".format(px), "{:.9f}".format(py),
                    "{:.9f}".format(pz), "{:.9f}".format(roll),
                    "{:.9f}".format(pitch), "{:.9f}".format(yaw),
                    "{:.6f}".format(math.degrees(yaw)),
                ])
                count += 1
    return count


def inspect_waypoint_csv(path):
    """Check the basic layout and sanity of an offline Waypoint v3 CSV.

    This is deliberately not a vehicle safety or collision check.
    Returns (count, planar_length_m, max_velocity_kmh).
    """
    required = ("x", "y", "z", "yaw", "velocity", "change_flag")
    points = []
    with open(path, "rb") as raw_stream:
        if raw_stream.readline().endswith(b"\r\n"):
            raise ValueError(
                "Waypoint CSV 使用 CRLF 換行；Autoware.AI 1.14 的 waypoint_loader "
                "可能無法辨識 change_flag 欄位並因 stoi 崩潰。"
                "請重新產生 LF 格式的 Waypoint CSV。"
            )
    with open(path, "r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(required).issubset(set(reader.fieldnames or [])):
            raise ValueError("Waypoint CSV 必須含 x,y,z,yaw,velocity,change_flag 欄位")
        for row_id, row in enumerate(reader, start=2):
            try:
                values = [float(row[k]) for k in required]
            except (KeyError, TypeError, ValueError):
                raise ValueError("Waypoint CSV 第 {} 行數值無效".format(row_id))
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Waypoint CSV 第 {} 行含 NaN 或 Inf".format(row_id))
            if not 0 <= values[4] <= 20:
                raise ValueError("Waypoint CSV 第 {} 行的速度超出離線測試範圍 0–20 km/h".format(row_id))
            points.append(values)
    if len(points) < 3:
        raise ValueError("Waypoint CSV 至少需要 3 筆資料")
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                 for a, b in zip(points[:-1], points[1:]))
    if length < 1.0:
        raise ValueError("Waypoint 路徑長度不足 1 m")
    return len(points), length, max(p[4] for p in points)
