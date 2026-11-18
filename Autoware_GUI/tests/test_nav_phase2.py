"""Offline navigation integration tests; no ROS/Qt runtime required."""

import ast
import csv
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import yaml

from aw_gui_core import inspect_waypoint_csv
from convert_ndt_to_waypoints import convert


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class NavPhase2Tests(unittest.TestCase):
    def test_converter_matches_waypoint_loader_v3(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "ndt.csv")
            target = os.path.join(folder, "wps.csv")
            with open(source, "w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(("time_s", "x", "y", "z", "yaw"))
                for i in range(16):
                    writer.writerow((i * 0.1, i * 0.2, 0, 0, 0))
            stats = convert(__import__("pathlib").Path(source),
                            __import__("pathlib").Path(target))
            self.assertEqual(stats[0], 16)
            count, length, top_speed = inspect_waypoint_csv(target)
            self.assertEqual(count, stats[1])
            self.assertAlmostEqual(length, 3.0)
            self.assertEqual(top_speed, 2.0)
            with open(target, "rb") as stream:
                content = stream.read()
            self.assertIn(b"change_flag\n", content)
            self.assertNotIn(b"\r\n", content)
            with open(target, newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(float(rows[0]["velocity"]), 0.0)
            self.assertEqual(float(rows[-1]["velocity"]), 0.0)

    def test_invalid_waypoint_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "bad.csv")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("x,y,z,yaw,velocity,change_flag\n"
                             "0,0,0,0,0,0\n1,0,0,0,NaN,0\n2,0,0,0,0,0\n")
            with self.assertRaises(ValueError):
                inspect_waypoint_csv(path)

    def test_crlf_waypoint_rejected_before_ros_loader_crash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "crlf.csv")
            with open(path, "wb") as stream:
                stream.write(b"x,y,z,yaw,velocity,change_flag\r\n"
                             b"0,0,0,0,0,0\r\n"
                             b"1,0,0,0,2,0\r\n"
                             b"2,0,0,0,0,0\r\n")
            with self.assertRaisesRegex(ValueError, "CRLF"):
                inspect_waypoint_csv(path)

    def test_nav_launch_is_offline_only(self):
        path = os.path.join(ROOT, "launch", "offline_pure_pursuit.launch")
        tree = ET.parse(path)
        nodes = tree.findall("node")
        self.assertEqual({n.attrib["pkg"] for n in nodes},
                         {"pure_pursuit", "twist_filter"})
        remaps = {r.attrib["from"]: r.attrib["to"]
                  for node in nodes for r in node.findall("remap")}
        self.assertEqual(remaps["/twist_raw"], "/offline_nav/twist_raw")
        self.assertEqual(remaps["/twist_cmd"], "/offline_nav/twist_cmd")
        self.assertEqual(remaps["/final_waypoints"], "/offline_nav/final_waypoints")

    def test_gui_has_fifth_navigation_tab_and_shutdown(self):
        path = os.path.join(ROOT, "autoware_student_gui.py")
        with open(path, encoding="utf-8") as stream:
            source = stream.read()
        ast.parse(source)
        self.assertIn("05  Waypoint / 導航測試", source)
        self.assertIn('"nav_controller", "nav_loader", "nav_bridge"', source)
        self.assertIn("def stop_nav_test", source)

    def test_navigation_rviz_button_uses_dedicated_profile(self):
        gui_path = os.path.join(ROOT, "autoware_student_gui.py")
        with open(gui_path, encoding="utf-8") as stream:
            source = stream.read()
        self.assertIn('self.button("開啟導航 RViz", self.open_nav_rviz', source)
        self.assertIn('os.path.join(APP_ROOT, "rviz", "navigation.rviz")', source)
        self.assertIn('self.spawn("nav_rviz", ["rviz", "-d", cfg])', source)

        config_path = os.path.join(ROOT, "rviz", "navigation.rviz")
        with open(config_path, encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        manager = config["Visualization Manager"]
        self.assertEqual(manager["Global Options"]["Fixed Frame"], "map")
        displays = {display["Name"]: display for display in manager["Displays"]}
        self.assertEqual(displays["Waypoint Path (full route)"]["Class"],
                         "rviz/Path")
        self.assertEqual(displays["Waypoint Path (full route)"]["Topic"],
                         "/offline_nav/waypoint_path")
        self.assertEqual(displays["NDT Pose"]["Topic"], "/ndt_pose")
        for name, topic in (
                ("Lookahead Target", "/next_target_mark"),
                ("Next Waypoint", "/next_waypoint_mark"),
                ("Lookahead Search Circle", "/search_circle_mark"),
                ("Pursuit Trajectory Circle", "/trajectory_circle_mark")):
            self.assertEqual(displays[name]["Class"], "rviz/Marker")
            self.assertEqual(displays[name]["Marker Topic"], topic)

    def test_twist_filter_config_sets_nonzero_jerk_limit(self):
        """An omitted ROS float defaults to zero and blocks angular motion."""
        path = os.path.join(ROOT, "autoware_student_gui.py")
        with open(path, encoding="utf-8") as stream:
            tree = ast.parse(stream.read())
        publish_config = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "publish_nav_config")
        assignment = next(
            node for node in publish_config.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name)
                    and target.id == "filter_payload"
                    for target in node.targets))
        payload = ast.literal_eval(assignment.value)
        self.assertGreater(payload["lateral_accel_limit"], 0.0)
        self.assertGreater(payload["lateral_jerk_limit"], 0.0)
        self.assertEqual(payload["lowpass_gain_angular_z"], 0.0)

    def test_bridge_republishes_lane_each_ros_timer_tick(self):
        """Pure Pursuit needs a new Lane callback after every control cycle."""
        publishers = {}

        class FakePublisher(object):
            def __init__(self, name, _message_type, **kwargs):
                self.messages = []
                self.latch = kwargs.get("latch", False)
                publishers[name] = self

            def publish(self, msg):
                self.messages.append(msg)

        class FakeWaypoint(object):
            def __init__(self, index, total):
                point = types.SimpleNamespace(x=index * 0.5, y=0.0)
                self.pose = types.SimpleNamespace(
                    pose=types.SimpleNamespace(position=point))
                speed = 0.0 if index in (0, total - 1) else 2.0 / 3.6
                self.twist = types.SimpleNamespace(
                    twist=types.SimpleNamespace(
                        linear=types.SimpleNamespace(x=speed)))

        class FakeLane(object):
            def __init__(self, count=0):
                self.waypoints = [FakeWaypoint(i, count)
                                  for i in range(count)]

        class FakeLaneArray(object):
            def __init__(self, lanes):
                self.lanes = lanes

        rospy = types.ModuleType("rospy")
        rospy.Publisher = FakePublisher
        rospy.Subscriber = lambda *args, **kwargs: None
        rospy.Duration = lambda seconds: seconds
        rospy.Timer = lambda interval, callback: (interval, callback)
        rospy.logwarn = lambda *args: None
        rospy.loginfo = lambda *args: None

        autoware_msgs = types.ModuleType("autoware_msgs")
        autoware_msgs_msg = types.ModuleType("autoware_msgs.msg")
        autoware_msgs_msg.Lane = FakeLane
        autoware_msgs_msg.LaneArray = FakeLaneArray
        geometry_msgs = types.ModuleType("geometry_msgs")
        geometry_msgs_msg = types.ModuleType("geometry_msgs.msg")
        class FakePoseStamped(object):
            def __init__(self, x, y):
                self.pose = types.SimpleNamespace(
                    position=types.SimpleNamespace(x=x, y=y))
                self.header = types.SimpleNamespace(stamp=None)

        class FakeTwistStamped(object):
            def __init__(self):
                self.header = None
                self.twist = types.SimpleNamespace(
                    linear=types.SimpleNamespace(x=0.0))

        geometry_msgs_msg.PoseStamped = FakePoseStamped
        geometry_msgs_msg.TwistStamped = FakeTwistStamped

        nav_msgs = types.ModuleType("nav_msgs")
        nav_msgs_msg = types.ModuleType("nav_msgs.msg")
        class FakePath(object):
            def __init__(self):
                self.header = types.SimpleNamespace(frame_id="")
                self.poses = []

        nav_msgs_msg.Path = FakePath

        modules = {
            "rospy": rospy,
            "autoware_msgs": autoware_msgs,
            "autoware_msgs.msg": autoware_msgs_msg,
            "geometry_msgs": geometry_msgs,
            "geometry_msgs.msg": geometry_msgs_msg,
            "nav_msgs": nav_msgs,
            "nav_msgs.msg": nav_msgs_msg,
        }
        bridge_path = os.path.join(ROOT, "offline_nav_bridge.py")
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location(
                "offline_nav_bridge_test", bridge_path)
            bridge_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge_module)
            bridge = bridge_module.OfflineNavBridge()

        route_pub = publishers["/offline_nav/final_waypoints"]
        self.assertTrue(route_pub.latch)
        interval, tick = bridge.route_timer
        self.assertAlmostEqual(interval, 0.1)
        tick(None)
        self.assertEqual(len(route_pub.messages), 0)

        original_lane = FakeLane(49)
        bridge.on_lanes(FakeLaneArray([original_lane]))
        self.assertEqual(len(route_pub.messages), 1)
        path_pub = publishers["/offline_nav/waypoint_path"]
        self.assertTrue(path_pub.latch)
        self.assertEqual(len(path_pub.messages), 1)
        self.assertEqual(path_pub.messages[0].header.frame_id, "map")
        self.assertEqual(len(path_pub.messages[0].poses), 49)
        self.assertIsNot(route_pub.messages[0], original_lane)
        for _ in range(3):
            tick(None)
        self.assertEqual(len(route_pub.messages), 4)
        self.assertTrue(all(len(msg.waypoints) == 49
                            for msg in route_pub.messages))

        bridge.on_pose(FakePoseStamped(5.0, 0.0))
        tick(None)
        moving_lane = route_pub.messages[-1]
        self.assertEqual(len(moving_lane.waypoints), 39)
        self.assertAlmostEqual(
            moving_lane.waypoints[0].pose.pose.position.x, 5.0)
        self.assertAlmostEqual(
            moving_lane.waypoints[0].twist.twist.linear.x, 2.0 / 3.6)

        bridge.current_pose_xy = (24.0, 0.0)
        tick(None)
        stop_lane = route_pub.messages[-1]
        self.assertEqual(len(stop_lane.waypoints), 3)
        self.assertEqual(stop_lane.waypoints[0].twist.twist.linear.x, 0.0)
        self.assertEqual(original_lane.waypoints[0].twist.twist.linear.x, 0.0)
        # The displayed global route remains complete as the local Lane shrinks.
        self.assertEqual(len(path_pub.messages), 1)
        self.assertEqual(len(path_pub.messages[0].poses), 49)


if __name__ == "__main__":
    unittest.main()
