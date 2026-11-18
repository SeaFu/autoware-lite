"""Regression test for ROS bag PTY cleanup, without requiring PyQt5."""

import ast
import os
import pty
import signal
import sys
import unittest


def load_owned_process():
    target = os.path.join(os.path.dirname(__file__), "..", "autoware_student_gui.py")
    with open(target, encoding="utf-8") as stream:
        tree = ast.parse(stream.read(), filename=target)
    node = next(item for item in tree.body
                if isinstance(item, ast.ClassDef) and item.name == "OwnedProcess")
    if sys.version_info >= (3, 8):
        module = ast.Module(body=[node], type_ignores=[])
    else:
        module = ast.Module(body=[node])
    scope = {"os": os, "signal": signal}
    exec(compile(module, target, "exec"), scope)
    return scope["OwnedProcess"]


class ProcessCleanupTests(unittest.TestCase):
    def test_pty_fd_is_closed_once_and_idempotent(self):
        OwnedProcess = load_owned_process()
        master, slave = pty.openpty()
        os.close(slave)
        try:
            obj = OwnedProcess("bag", None, stream=master, stdin_pty=master)
            obj.close_files()
            self.assertIsNone(obj.stream)
            self.assertIsNone(obj.stdin_pty)
            with self.assertRaises(OSError):
                os.fstat(master)
            obj.close_files()
        finally:
            try:
                os.close(master)
            except OSError:
                pass

    def test_regular_stream_closes(self):
        OwnedProcess = load_owned_process()
        read_fd, write_fd = os.pipe()
        stream = os.fdopen(read_fd, "rb")
        try:
            obj = OwnedProcess("mapping", None, stream=stream)
            obj.close_files()
            self.assertTrue(stream.closed)
            self.assertIsNone(obj.stream)
        finally:
            os.close(write_fd)


if __name__ == "__main__":
    unittest.main()
