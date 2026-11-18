"""Check GUI text scaling without importing PyQt or needing a ROS display."""

import ast
import os
import unittest


class TypographyTests(unittest.TestCase):
    def test_default_size_and_uniform_scaling(self):
        path = os.path.join(os.path.dirname(__file__), "..", "autoware_student_gui.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        gui_class = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                         and node.name == "StudentGUI")
        style_assignment = next(
            node for node in ast.walk(gui_class)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Attribute) and target.attr == "ui_style_template"
                    for target in node.targets)
        )
        template = ast.literal_eval(style_assignment.value)
        self.assertIn("font-size:__BASE__px", template)
        self.assertIn("font-size:__LOG__px", template)
        method = next(node for node in gui_class.body
                      if isinstance(node, ast.FunctionDef) and node.name == "apply_text_size")
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), path, "exec"), namespace)

        class FakeSettings:
            def __init__(self):
                self.values = {}

            def setValue(self, key, value):
                self.values[key] = value

        class FakeGUI:
            def __init__(self):
                self.ui_style_template = template
                self.settings = FakeSettings()

            def setStyleSheet(self, css):
                self.css = css

        fake = FakeGUI()
        namespace["apply_text_size"](fake, 17)
        self.assertIn("font-size:17px", fake.css)
        self.assertIn("font-size:15px", fake.css)
        self.assertIn("font-size:28px", fake.css)
        self.assertEqual(fake.settings.values["ui_font_px"], 17)
        self.assertNotIn("__BASE__", fake.css)
        namespace["apply_text_size"](fake, 20)
        self.assertIn("font-size:20px", fake.css)
        self.assertIn("font-size:18px", fake.css)
        self.assertEqual(fake.settings.values["ui_font_px"], 20)


if __name__ == "__main__":
    unittest.main()
