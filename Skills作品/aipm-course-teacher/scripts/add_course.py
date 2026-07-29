#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "references" / "courses"
CATALOG = ROOT / "references" / "course_catalog.md"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    if not value:
        raise ValueError("course id must contain at least one ASCII letter or digit")
    return value


def ensure_catalog() -> None:
    if CATALOG.exists():
        return
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(
        "# Course Catalog\n\n"
        "## Courses\n\n"
        "| Course ID | Course Name | Audience | Main File | Status |\n"
        "|---|---|---|---|---|\n",
        encoding="utf-8",
    )


def catalog_has(course_id: str) -> bool:
    if not CATALOG.exists():
        return False
    needle = f"| {course_id} |"
    return needle in CATALOG.read_text(encoding="utf-8")


def append_catalog(course_id: str, name: str, audience: str, status: str) -> None:
    ensure_catalog()
    if catalog_has(course_id):
        return
    rel = f"references/courses/{course_id}/course.md"
    with CATALOG.open("a", encoding="utf-8") as f:
        f.write(f"| {course_id} | {name} | {audience} | `{rel}` | {status} |\n")


def quality_passes(course_id: str) -> bool:
    checker = ROOT / "scripts" / "check_course_quality.py"
    if not checker.exists():
        return False
    result = subprocess.run(
        [sys.executable, str(checker), "--course", course_id, "--level", "standard"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a new course folder and catalog entry.")
    parser.add_argument("--id", required=True, help="ASCII course id, e.g. agent-product")
    parser.add_argument("--name", required=True)
    parser.add_argument("--audience", default="AI product manager learner")
    parser.add_argument("--source-md", help="Existing markdown file to copy as course.md")
    parser.add_argument("--start", default="", help="Recommended starting point")
    parser.add_argument("--active", action="store_true", help="Register as active only after quality check passes")
    args = parser.parse_args()

    course_id = slugify(args.id)
    course_dir = COURSES / course_id
    course_dir.mkdir(parents=True, exist_ok=True)
    course_md = course_dir / "course.md"
    manifest = course_dir / "manifest.md"

    if args.source_md:
        src = Path(args.source_md).expanduser().resolve()
        if not src.exists():
            print(f"source markdown not found: {src}")
            return 1
        shutil.copy2(src, course_md)
    elif not course_md.exists():
        course_md.write_text(f"# {args.name}\n\nTODO: Add course content.\n", encoding="utf-8")

    if not manifest.exists():
        manifest.write_text(
            f"# Course Manifest: {course_id}\n\n"
            f"Course name: {args.name}\n\n"
            f"Audience:\n\n- {args.audience}\n\n"
            "Teaching goals:\n\n"
            "1. Understand the core concepts.\n"
            "2. Apply them to AI product management decisions.\n"
            "3. Practice interview-ready explanations.\n"
            "4. Build toward a portfolio project.\n\n"
            f"Recommended starting point:\n\n- {args.start or 'Start from the first conceptual section.'}\n\n"
            "Project path:\n\n- TBD\n",
            encoding="utf-8",
        )

    status = "draft"
    if args.active:
        if not quality_passes(course_id):
            print("quality check failed; registering as draft instead of active")
        else:
            status = "active"

    append_catalog(course_id, args.name, args.audience, status)
    print(course_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
