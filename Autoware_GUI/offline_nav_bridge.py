#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""ROS Melodic (Python 2): bridge a recorded NDT trajectory to offline nav.

No motor/CAN topics are published. This is only a demonstration of the
waypoint -> Pure Pursuit -> Twist command-generation chain. It is not an
obstacle-avoidance planner and must not be used to drive a real vehicle.
"""

from __future__ import print_function

import copy
import math

import rospy
from autoware_msgs.msg import Lane, LaneArray
from geometry_msgs.msg import PoseStamped, TwistStamped
from nav_msgs.msg import Path


class OfflineNavBridge(object):
    # Autoware.AI 1.14 Pure Pursuit resets its received-waypoint flag after
    # each calculation, so a one-time latched publication is not sufficient.
    ROUTE_PUBLISH_HZ = 10.0

    def __init__(self):
        self.pose_pub = rospy.Publisher(
            "/offline_nav/current_pose", PoseStamped, queue_size=10)
        self.velocity_pub = rospy.Publisher(
            "/offline_nav/current_velocity", TwistStamped, queue_size=10)
        self.lane_pub = rospy.Publisher(
            "/offline_nav/final_waypoints", Lane, queue_size=1, latch=True)
        # A complete, fixed visualization path. Unlike final_waypoints, this
        # never shrinks as the recorded NDT pose advances along the route.
        self.path_pub = rospy.Publisher(
            "/offline_nav/waypoint_path", Path, queue_size=1, latch=True)
        self.last_position = None
        self.last_stamp = None
        self.latest_velocity = None
        self.latest_velocity_walltime = None
        self.current_route = None
        self.current_pose_xy = None
        rospy.Subscriber("/based/lane_waypoints_raw", LaneArray, self.on_lanes,
                         queue_size=1)
        rospy.Subscriber("/ndt_pose", PoseStamped, self.on_pose, queue_size=10)
        rospy.Subscriber("/estimate_twist", TwistStamped, self.on_twist,
                         queue_size=10)
        # ROS-time timer: pauses together with rosbag --clock --pause.
        self.route_timer = rospy.Timer(
            rospy.Duration(1.0 / self.ROUTE_PUBLISH_HZ),
            self.publish_route_periodically)
        rospy.logwarn("Offline bridge: only /offline_nav/* outputs; NO vehicle control")

    def on_lanes(self, msg):
        if not msg.lanes:
            rospy.logwarn("waypoint_loader published an empty LaneArray")
            return
        lane = msg.lanes[0]
        if len(lane.waypoints) < 3:
            rospy.logwarn("Need >=3 waypoints for offline Pure Pursuit")
            return
        self.current_route = copy.deepcopy(lane)
        path = Path()
        path.header.frame_id = "map"
        path.poses = [copy.deepcopy(wp.pose) for wp in lane.waypoints]
        self.path_pub.publish(path)
        # Publish immediately as well; the latched copy serves late joiners.
        self.lane_pub.publish(self.current_route)
        rospy.loginfo("Offline route ready: %d waypoints", len(lane.waypoints))

    def publish_route_periodically(self, _event):
        if self.current_route is not None:
            self.lane_pub.publish(self.make_local_lane())

    def make_local_lane(self):
        """Present a forward-moving route, as Autoware's final_waypoints does.

        Pure Pursuit uses the *first* waypoint's velocity as its command. A
        permanently republished full CSV would keep commanding the initial
        zero-speed waypoint even after the recorded vehicle moves past it.
        """
        lane = copy.deepcopy(self.current_route)
        if self.current_pose_xy is None:
            return lane

        px, py = self.current_pose_xy
        waypoints = lane.waypoints
        nearest = min(
            range(len(waypoints)),
            key=lambda index: (
                (waypoints[index].pose.pose.position.x - px) ** 2 +
                (waypoints[index].pose.pose.position.y - py) ** 2))

        # Retain >=3 points; the Pure Pursuit implementation requires them.
        first = min(nearest, len(waypoints) - 3)
        lane.waypoints = waypoints[first:]

        # The final point in the recorded CSV is a stop point. If the closest
        # point is among the final two, command zero speed instead of reusing
        # the third-to-last point's nonzero speed.
        if nearest >= len(waypoints) - 2:
            lane.waypoints[0].twist.twist.linear.x = 0.0
        return lane

    def on_twist(self, msg):
        self.latest_velocity = msg
        self.latest_velocity_walltime = rospy.get_time()

    def on_pose(self, pose):
        self.current_pose_xy = (pose.pose.position.x, pose.pose.position.y)
        self.pose_pub.publish(pose)
        velocity = TwistStamped()
        velocity.header = pose.header
        # Prefer Autoware's NDT velocity estimate if it is recent. Fallback to
        # finite differences to keep a meaningful input when estimate_twist is
        # unavailable in a particular build. No actuation happens here.
        if (self.latest_velocity is not None
                and self.latest_velocity_walltime is not None
                and abs(rospy.get_time() - self.latest_velocity_walltime) < 0.8):
            velocity.twist = copy.deepcopy(self.latest_velocity.twist)
        elif self.last_position is not None and self.last_stamp is not None:
            dt = (pose.header.stamp - self.last_stamp).to_sec()
            if 0.02 < dt < 2.0:
                dx = pose.pose.position.x - self.last_position[0]
                dy = pose.pose.position.y - self.last_position[1]
                if math.hypot(dx, dy) < 1.5:
                    velocity.twist.linear.x = min(3.0, math.hypot(dx, dy) / dt)
        self.velocity_pub.publish(velocity)
        self.last_position = (pose.pose.position.x, pose.pose.position.y)
        self.last_stamp = pose.header.stamp


if __name__ == "__main__":
    rospy.init_node("offline_nav_bridge", anonymous=False)
    OfflineNavBridge()
    rospy.spin()
