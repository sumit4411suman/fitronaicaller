"""Verify the generated theme files still match packages/brand/tokens.json (run in CI and before release)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tokens = json.loads((ROOT / "packages/brand/tokens.json").read_text())["colors"]
problems: list[str] = []
qss = (ROOT / "packages/brand/qt/theme.qss").read_text()
for key in ("background", "gold", "text_primary", "emergency_stop"):
    if tokens[key].upper() not in qss.upper():
        problems.append(f"theme.qss missing {key} {tokens[key]}")
for f in list((ROOT / "apps").rglob("colors.xml")) + [ROOT / "packages/brand/android/colors.xml"]:
    xml = f.read_text()
    for name, val in tokens.items():
        m = re.search(rf'name="brand_{name}">(#[0-9A-Fa-f]{{6}})<', xml)
        if not m or m.group(1).upper() != val.upper():
            problems.append(f"{f.relative_to(ROOT)}: brand_{name} != {val}")
for f in list((ROOT / "apps").rglob("BrandTheme.kt")) + [ROOT / "packages/brand/android/BrandTheme.kt"]:
    kt = f.read_text()
    for name, val in tokens.items():
        if f"0XFF{val[1:].upper()}" not in kt.upper():
            problems.append(f"{f.relative_to(ROOT)}: missing {name} {val}")
if problems:
    print("\n".join(problems))
    sys.exit(1)
print("brand tokens in sync")
