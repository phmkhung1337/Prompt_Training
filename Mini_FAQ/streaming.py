"""Extract only a progressively available JSON answer string for display."""

import json
import re


class AnswerStream:
    def __init__(self, callback):
        self.callback = callback
        self.raw = ""
        self.visible = ""

    def feed(self, delta: str) -> None:
        self.raw += delta
        if not self.callback:
            return
        match = re.search(r'"answer"\s*:\s*"', self.raw)
        if not match:
            return
        tail = self.raw[match.end():]
        # Decode complete JSON string units; hold incomplete escape/unicode units.
        parts, i = [], 0
        while i < len(tail):
            c = tail[i]
            if c == '"':
                break
            if c == "\\":
                if i + 1 >= len(tail):
                    break
                length = 6 if tail[i + 1] == "u" else 2
                if i + length > len(tail):
                    break
                unit = tail[i:i + length]
                # A surrogate pair must arrive completely before display.
                if length == 6 and re.fullmatch(r"\\u[dD][89aAbB][0-9a-fA-F]{2}", unit):
                    if i + 12 > len(tail):
                        break
                    unit = tail[i:i + 12]
                    length = 12
                try:
                    parts.append(json.loads('"' + unit + '"'))
                except ValueError:
                    break
                i += length
            else:
                parts.append(c)
                i += 1
        visible = "".join(parts)
        if visible.startswith(self.visible) and len(visible) > len(self.visible):
            self.callback(visible[len(self.visible):])
            self.visible = visible
