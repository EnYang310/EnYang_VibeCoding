#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references" / "course_catalog.md"


def parse_catalog() -> list[dict[str, str]]:
    if not CATALOG.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if (
            not s.startswith("|")
            or "---" in s
            or "Course ID" in s
            or "课程 ID" in s
            or "课程名称" in s
        ):
            continue
        cells = [c.strip().strip("`") for c in s.strip("|").split("|")]
        if len(cells) >= 5:
            rows.append({
                "id": cells[0],
                "name": cells[1],
                "audience": cells[2],
                "file": cells[3],
                "status": cells[4],
            })
    return rows


def main() -> int:
    rows = parse_catalog()
    if not rows:
        print("暂无已注册课程。")
        return 0
    print("课程 ID\t状态\t课程名称\t主文件")
    for row in rows:
        print(f"{row['id']}\t{row['status']}\t{row['name']}\t{row['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
