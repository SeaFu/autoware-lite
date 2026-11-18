#!/usr/bin/env python3
"""Convert Autoware_GUI's cleaned NDT pose CSV into Autoware.AI Waypoint v3.

Designed for **offline inspection and command-generation tests**, not for
unreviewed real-vehicle operation. Compatible with Python 3.6 (Ubuntu 18.04).
No ROS or third-party Python package is required.
"""

import argparse
import csv
import math
import statistics
import sys
from pathlib import Path


INPUT_FIELDS = ("time_s", "x", "y", "z", "yaw")
OUTPUT_FIELDS = ("x", "y", "z", "yaw", "velocity", "change_flag")


class RouteError(Exception):
    """Invalid trajectory or conversion settings."""


def distance(a, b):
    return math.hypot(b["x"] - a["x"], b["y"] - a["y"])


def wrap_angle(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def read_ndt_csv(path):
    points = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        present = set(reader.fieldnames or [])
        missing = set(INPUT_FIELDS) - present
        if missing:
            raise RouteError("輸入 CSV 缺少欄位：" + ", ".join(sorted(missing)))
        for row_no, row in enumerate(reader, start=2):
            try:
                point = {field: float(row[field]) for field in INPUT_FIELDS}
            except (ValueError, TypeError, KeyError):
                raise RouteError("第 {} 行含有無法解析的數值".format(row_no))
            if not all(math.isfinite(value) for value in point.values()):
                raise RouteError("第 {} 行含有 NaN 或無限大".format(row_no))
            point["line"] = row_no
            if points and point["time_s"] <= points[-1]["time_s"]:
                raise RouteError("第 {} 行時間未嚴格遞增".format(row_no))
            points.append(point)
    if len(points) < 3:
        raise RouteError("至少需要三筆有效姿態資料")
    return points


def inspect_route(points, max_jump_m):
    total_length = 0.0
    jumps = []
    for previous, current in zip(points[:-1], points[1:]):
        segment = distance(previous, current)
        total_length += segment
        if segment > max_jump_m:
            jumps.append((previous["line"], current["line"], segment))
    if jumps:
        details = "; ".join("{}→{}: {:.2f}m".format(a, b, d)
                            for a, b, d in jumps[:5])
        raise RouteError(
            "偵測到相鄰姿態異常位移（>{:.2f}m）：{}。"
            "請先檢查 NDT 路徑，不要直接轉成導航路線。".format(max_jump_m, details)
        )
    if total_length < 1.0:
        raise RouteError("總軌跡長度不足 1 m，不適合產生導航路徑")
    return total_length


def downsample(points, spacing_m):
    selected = [points[0]]
    accumulated = 0.0
    for previous, current in zip(points[:-2], points[1:-1]):
        accumulated += distance(previous, current)
        if accumulated >= spacing_m and distance(selected[-1], current) >= 0.05:
            selected.append(current)
            accumulated = 0.0

    last = points[-1]
    if distance(selected[-1], last) >= 0.05:
        selected.append(last)
    elif selected[-1] is not points[0]:
        selected[-1] = last

    if len(selected) < 3:
        raise RouteError("取樣後不足三個 Waypoint，請減少 --spacing-m")
    return selected


def heading_consistency(points):
    differences = []
    for previous, current in zip(points[:-1], points[1:]):
        if distance(previous, current) < 0.1:
            continue
        direction = math.atan2(current["y"] - previous["y"],
                               current["x"] - previous["x"])
        differences.append(abs(math.degrees(wrap_angle(previous["yaw"] - direction))))
    return statistics.median(differences) if differences else 0.0


def convert(input_path, output_path, spacing_m=0.5, speed_kmh=2.0,
            max_jump_m=1.5):
    if spacing_m <= 0.0 or max_jump_m <= 0.0:
        raise RouteError("--spacing-m 與 --max-jump-m 必須大於 0")
    if speed_kmh <= 0.0 or speed_kmh > 20.0:
        raise RouteError("離線測試速度 --speed-kmh 必須在 (0, 20] km/h")
    if input_path.resolve() == output_path.resolve():
        raise RouteError("輸入與輸出檔案不能相同")
    if output_path.exists():
        raise RouteError("輸出檔案已存在，請另選檔名以避免覆蓋：" + str(output_path))

    points = read_ndt_csv(input_path)
    total_length = inspect_route(points, max_jump_m)
    selected = downsample(points, spacing_m)
    median_angle = heading_consistency(selected)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create: do not silently overwrite an earlier route.
    with output_path.open("x", encoding="utf-8", newline="") as stream:
        # Autoware.AI 1.14's waypoint_loader preserves a trailing CR from
        # CRLF headers, so "change_flag\r" is not matched as "change_flag".
        # That leads to std::stoi("") and aborts the loader. Write LF only.
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(OUTPUT_FIELDS)
        for index, point in enumerate(selected):
            # The first/last waypoints are stop points, not a complete braking
            # profile. A vehicle-grade planner must verify speeds separately.
            speed = 0.0 if index in (0, len(selected) - 1) else speed_kmh
            writer.writerow((
                "{:.6f}".format(point["x"]),
                "{:.6f}".format(point["y"]),
                "{:.6f}".format(point["z"]),
                "{:.6f}".format(wrap_angle(point["yaw"])),
                "{:.3f}".format(speed),
                "0",
            ))

    return len(points), len(selected), total_length, median_angle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="GUI 整理後的 NDT CSV")
    parser.add_argument("--output", required=True, type=Path, help="輸出 Waypoint v3 CSV")
    parser.add_argument("--spacing-m", type=float, default=0.5,
                        help="距離取樣間隔（預設 0.5 m）")
    parser.add_argument("--speed-kmh", type=float, default=2.0,
                        help="離線測試目標速度 km/h（預設 2.0）")
    parser.add_argument("--max-jump-m", type=float, default=1.5,
                        help="相鄰定位點最大合理距離（預設 1.5 m）")
    args = parser.parse_args(argv)
    try:
        count, chosen, length, angle = convert(
            args.input, args.output, args.spacing_m, args.speed_kmh, args.max_jump_m
        )
    except (OSError, RouteError) as error:
        print("[錯誤] {}".format(error), file=sys.stderr)
        return 1

    print("[完成] {}".format(args.output))
    print("原始 {} 筆 → Waypoint {} 筆；估計路徑長度 {:.2f} m".format(
        count, chosen, length))
    print("內部速度欄位：{:.2f} km/h；首尾點速度：0 km/h".format(args.speed_kmh))
    print("姿態 yaw 與路徑切線方向差值中位數：{:.1f}°".format(angle))
    if angle > 60.0:
        print("[警告] yaw 和移動方向差異偏大；請檢查 TF、倒車與軌跡方向。")
    print("[提醒] 此檔僅供離線導航節點測試，尚未驗證實車安全。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
