#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "state" / "daily"


def note_path() -> Path:
    DAILY.mkdir(parents=True, exist_ok=True)
    p = DAILY / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    if not p.exists():
        p.write_text(f"# Learning Note {p.stem}\n\n", encoding="utf-8")
    return p


def bullet_block(title: str, value: str) -> str:
    value = value.strip()
    if not value:
        value = "未记录"
    return f"- {title}: {value}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a structured lesson archive to today's daily note.")
    parser.add_argument("--course", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--status", default="complete")
    parser.add_argument("--covered", default="")
    parser.add_argument("--understanding", default="")
    parser.add_argument("--confusions", default="")
    parser.add_argument("--quiz", default="")
    parser.add_argument("--memorize", default="")
    parser.add_argument("--assignment", default="")
    parser.add_argument("--next", default="")
    args = parser.parse_args()

    p = note_path()
    now = datetime.now().strftime("%H:%M")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"## Lesson Archive {now}\n\n")
        f.write(bullet_block("Course", args.course))
        f.write(bullet_block("Topic", args.topic))
        f.write(bullet_block("Status", args.status))
        f.write(bullet_block("Covered", args.covered))
        f.write(bullet_block("User understanding", args.understanding))
        f.write(bullet_block("Confusions", args.confusions))
        f.write(bullet_block("Quiz", args.quiz))
        f.write(bullet_block("Strong answer to memorize", args.memorize))
        f.write(bullet_block("Assignment", args.assignment))
        f.write(bullet_block("Next recommendation", args.next))
        f.write("\n")
    print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

