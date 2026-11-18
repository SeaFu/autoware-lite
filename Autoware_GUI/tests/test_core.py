import csv
import json
import math
import os
import tempfile
import unittest

from aw_gui_core import (
    compact_ros_lines, convert_pose_csv, linux_path, mapping_config, match_config,
    ndt_config_command, quaternion_rpy, parse_bag_progress, shell_command,
    tf_arguments,
)


class CoreTests(unittest.TestCase):
    def test_windows_and_linux_paths(self):
        self.assertEqual(linux_path(r"D:\VLP16\mapping.bag"), "/mnt/d/VLP16/mapping.bag")
        self.assertEqual(linux_path("/mnt/d/VLP16/mapping.bag"), "/mnt/d/VLP16/mapping.bag")
        self.assertTrue(linux_path("~/autoware.ai").endswith("/autoware.ai"))

    def test_quote_shell_arguments(self):
        text = shell_command("/tmp/my workspace", ["rosbag", "play", "/mnt/d/a b.bag"])
        self.assertIn("'/tmp/my workspace/install/setup.bash'", text)
        self.assertIn("'/mnt/d/a b.bag'", text)
        self.assertIn("/opt/ros/melodic/setup.bash", text)

    def test_tf_order(self):
        args = tf_arguments({"x": 1, "y": 2, "z": 3, "roll": 0.1, "pitch": 0.2, "yaw": 0.3})
        self.assertEqual(args[:3], ["rosrun", "tf", "static_transform_publisher"])
        self.assertEqual(args[3:], ["1", "2", "3", "0.3", "0.2", "0.1", "base_link", "velodyne", "100"])

    def test_matching_config(self):
        self.assertEqual(match_config()["init_pos_gnss"], 0)
        self.assertEqual(match_config()["resolution"], 1.0)

    def test_mapping_config_matches_legacy_defaults(self):
        self.assertEqual(mapping_config(), {
            "resolution": 1.0, "step_size": 0.1, "trans_epsilon": 0.01,
            "max_iterations": 30, "leaf_size": 2.0, "min_scan_range": 5.0,
            "max_scan_range": 200.0, "min_add_scan_shift": 1.0,
        })

    def test_ndt_updates_preserve_mode_fields(self):
        mapping = mapping_config({"resolution": 1.5, "leaf_size": 0.5})
        self.assertEqual(mapping["resolution"], 1.5)
        self.assertEqual(mapping["leaf_size"], 0.5)
        self.assertEqual(mapping["max_iterations"], 30)
        matching = match_config({"step_size": 0.25, "max_iterations": 50})
        self.assertEqual(matching["step_size"], 0.25)
        self.assertEqual(matching["max_iterations"], 50)
        self.assertEqual(matching["init_pos_gnss"], 0)
        self.assertEqual((matching["x"], matching["y"], matching["yaw"]), (0, 0, 0))

    def test_ndt_config_commands_for_both_modes(self):
        mapping_cmd = ndt_config_command("mapping", mapping_config({"resolution": 1.7}))
        self.assertEqual(mapping_cmd[:5], [
            "rostopic", "pub", "-1", "/config/ndt_mapping",
            "autoware_config_msgs/ConfigNDTMapping",
        ])
        self.assertEqual(json.loads(mapping_cmd[5])["resolution"], 1.7)
        matching_cmd = ndt_config_command("matching", match_config({"resolution": 2.0}))
        self.assertEqual(matching_cmd[:5], [
            "rostopic", "pub", "-1", "/config/ndt", "autoware_config_msgs/ConfigNDT",
        ])
        self.assertEqual(json.loads(matching_cmd[5])["resolution"], 2.0)

    def test_ndt_config_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            mapping_config({"min_scan_range": 30.0, "max_scan_range": 10.0})
        with self.assertRaises(ValueError):
            mapping_config({"leaf_size": 0.0})
        with self.assertRaises(ValueError):
            match_config({"resolution": 0.0})
        with self.assertRaises(ValueError):
            match_config({"max_iterations": 0})
        with self.assertRaises(ValueError):
            mapping_config({"typo_field": 5})
        with self.assertRaises(ValueError):
            ndt_config_command("bad_mode", {})

    def test_bag_output_is_quiet_but_errors_remain(self):
        lines = ["[RUNNING] Bag Time: 1784268357.000000 Duration: 4.230000 / 49.210000",
                 "[ERROR] failed to open bag"]
        self.assertEqual(compact_ros_lines("bag", lines), ["[ERROR] failed to open bag"])
        self.assertEqual(compact_ros_lines("bag", lines, detailed=True), [lines[1]])

    def test_parse_bag_progress_updates_same_status(self):
        stream = ("\r [PAUSED] Bag Time: 1784268352.770000 Duration: 0.000000 / 49.210000 \r"
                  "\r [RUNNING] Bag Time: 1784268357.000000 Duration: 4.230000 / 49.210000 \r")
        status = parse_bag_progress(stream)
        self.assertFalse(status["paused"])
        self.assertAlmostEqual(status["elapsed"], 4.23)
        self.assertAlmostEqual(status["duration"], 49.21)
        self.assertIsNone(parse_bag_progress("Opening bag file ..."))

    def test_ndt_mapping_progress_is_sampled(self):
        lines = ["NDT has converged: 1", "(Processed/Input): (49 / 49)",
                 "(Processed/Input): (50 / 50)", "(Processed/Input): (51 / 51)"]
        self.assertEqual(compact_ros_lines("mapping", lines),
                         ["建圖進度：已處理 50 / 50 筆點雲"])

    def test_quaternion(self):
        r, p, yaw = quaternion_rpy(0, 0, math.sin(math.pi / 4), math.cos(math.pi / 4))
        self.assertAlmostEqual(r, 0)
        self.assertAlmostEqual(p, 0)
        self.assertAlmostEqual(yaw, math.pi / 2)

    def test_convert_pose_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_name = os.path.join(tmp, "pose_raw.csv")
            output_name = os.path.join(tmp, "pose.csv")
            with open(input_name, "w", newline="", encoding="utf-8") as fd:
                writer = csv.writer(fd)
                writer.writerow([
                    "%time", "field.header.seq",
                    "field.pose.position.x", "field.pose.position.y", "field.pose.position.z",
                    "field.pose.orientation.x", "field.pose.orientation.y",
                    "field.pose.orientation.z", "field.pose.orientation.w",
                ])
                writer.writerow(["1784268356902400000", 1, 1, 2, 3, 0, 0, 0, 1])
                writer.writerow(["1784268357002400000", 2, 2, 3, 4, 0, 0, 0, 1])
            n = convert_pose_csv(input_name, output_name)
            self.assertEqual(n, 2)
            with open(output_name, newline="", encoding="utf-8") as fd:
                rows = list(csv.DictReader(fd))
            self.assertEqual(rows[0]["x"], "1.000000000")
            self.assertAlmostEqual(float(rows[1]["time_s"]), 0.1, places=5)
            self.assertEqual(rows[1]["yaw_deg"], "0.000000")


if __name__ == "__main__":
    unittest.main()
