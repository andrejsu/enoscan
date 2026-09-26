from __future__ import annotations

import re


VINTAGE = re.compile(r"(?<![\d./-])(19[5-9]\d|20[0-2]\d)(?![\d]|[./-]\d)")


def extract_year(text: str) -> int | None:
    found = {int(match) for match in VINTAGE.findall(text)}
    return found.pop() if len(found) == 1 else None
