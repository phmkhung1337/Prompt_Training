import re
import unittest
from pathlib import Path

from ui_theme import theme_variables


def contrast(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    bright, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (bright + 0.05) / (dark + 0.05)


class ThemeTests(unittest.TestCase):
    def test_stylesheet_has_no_unresolved_tokens_in_either_mode(self):
        css = (Path(__file__).resolve().parents[1] / "ui.css").read_text(encoding="utf-8")
        used = set(re.findall(r"var\((--campus-[\w-]+)\)", css))
        for mode in ("Sáng", "Tối"):
            with self.subTest(mode=mode):
                variables, scheme = theme_variables(mode)
                self.assertFalse(used - variables.keys())
                self.assertIn(scheme, ("light", "dark"))

    def test_normal_text_and_action_labels_meet_contrast_in_both_modes(self):
        for mode in ("Sáng", "Tối"):
            variables, _ = theme_variables(mode)
            for foreground, background in (
                ("text", "bg"), ("text", "surface"), ("muted", "surface"),
                ("on-primary", "blue"), ("on-gradient", "gradient-start"),
                ("on-gradient", "gradient-end"),
            ):
                with self.subTest(mode=mode, foreground=foreground, background=background):
                    self.assertGreaterEqual(
                        contrast(variables[f"--campus-{foreground}"], variables[f"--campus-{background}"]),
                        4.5,
                    )
