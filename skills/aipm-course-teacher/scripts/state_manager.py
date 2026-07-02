#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "state" / "daily"


def today_path() -> Path:
    return DAILY / f"{datetime.now().strftime('%Y-%m-%d')}.md"


def ensure_today() -> Path:
    DAILY.mkdir(parents=True, exist_ok=True)
    p = today_path()
    if not p.exists():
        p.write_text(f"# Learning Note {p.stem}\n\n", encoding="utf-8")
    return p


def latest_path() -> Path | None:
    DAILY.mkdir(parents=True, exist_ok=True)
    files = sorted(DAILY.glob("*.md"))
    return files[-1] if files else None


def recent_three_days() -> str:
    DAILY.mkdir(parents=True, exist_ok=True)
    today = datetime.now().date()
    labels = [
        ("前天", today - timedelta(days=2)),
        ("昨天", today - timedelta(days=1)),
        ("今天", today),
    ]
    chunks: list[str] = []
    for label, day in labels:
        p = DAILY / f"{day.strftime('%Y-%m-%d')}.md"
        chunks.append(f"## {label} {p.stem}")
        if p.exists():
            content = p.read_text(encoding="utf-8").strip()
            chunks.append(content if content else "无记录")
        else:
            chunks.append("无记录")
        chunks.append("")
    return "\n".join(chunks).strip()


def append_session(course: str, topic: str, summary: str, status: str = "incomplete") -> Path:
    p = ensure_today()
    now = datetime.now().strftime("%H:%M")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"## Session {now}\n\n")
        f.write(f"- Course: {course}\n")
        f.write(f"- Topic: {topic}\n")
        f.write(f"- Status: {status}\n")
        f.write(f"- Summary: {summary}\n")
        f.write("- User understanding:\n")
        f.write("- Confusions:\n")
        f.write("- Quiz:\n")
        f.write("- Assignment:\n")
        f.write("- Next recommendation:\n\n")
    return p


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("today")
    sub.add_parser("latest")
    sub.add_parser("recent")
    start = sub.add_parser("start")
    start.add_argument("--course", required=True)
    start.add_argument("--topic", required=True)
    app = sub.add_parser("append")
    app.add_argument("--course", required=True)
    app.add_argument("--topic", required=True)
    app.add_argument("--summary", required=True)
    app.add_argument("--status", default="incomplete")
    args = parser.parse_args()

    if args.cmd == "today":
        print(ensure_today())
    elif args.cmd == "latest":
        p = latest_path()
        print(p if p else "No daily notes yet.")
    elif args.cmd == "recent":
        print(recent_three_days())
    elif args.cmd == "start":
        p = append_session(args.course, args.topic, "Class started.", "incomplete")
        print(p)
    elif args.cmd == "append":
        p = append_session(args.course, args.topic, args.summary, args.status)
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
