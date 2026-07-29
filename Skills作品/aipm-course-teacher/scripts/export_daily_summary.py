#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "state" / "daily"
OUT = ROOT / "state" / "summaries"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a combined learning summary from daily notes.")
    parser.add_argument("--from-date", dest="from_date", default="")
    parser.add_argument("--to-date", dest="to_date", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    files = sorted(DAILY.glob("*.md"))
    if args.from_date:
        files = [p for p in files if p.stem >= args.from_date]
    if args.to_date:
        files = [p for p in files if p.stem <= args.to_date]
    if not files:
        print("No daily notes matched.")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else OUT / f"summary_{files[0].stem}_to_{files[-1].stem}.md"
    lines = ["# Learning Summary", "", f"Range: {files[0].stem} to {files[-1].stem}", ""]
    for p in files:
        lines.append(f"## {p.stem}")
        content = p.read_text(encoding="utf-8").strip()
        lines.append(content)
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

