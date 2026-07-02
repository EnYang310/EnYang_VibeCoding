#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "scripts" / "extract_course_section.py"


def extract(course: str, query: str, max_lines: int) -> str:
    result = subprocess.run(
        [str(EXTRACT), "--course", course, "--query", query, "--max-lines", str(max_lines)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stdout.strip() or result.stderr.strip() or "extract failed")
    return result.stdout


def clean_heading(line: str) -> str:
    return re.sub(r"^#+\s*", "", line).strip()


def key_terms(text: str) -> list[str]:
    terms: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("###") or s.startswith("##"):
            h = clean_heading(s)
            if h and h not in terms:
                terms.append(h)
        for m in re.finditer(r"`([^`]{2,40})`", s):
            term = m.group(1).strip()
            if term and term not in terms:
                terms.append(term)
    return terms[:6]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a small quiz from a course section.")
    parser.add_argument("--course", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--max-lines", type=int, default=120)
    args = parser.parse_args()

    text = extract(args.course, args.query, args.max_lines)
    terms = key_terms(text)
    main_term = terms[0] if terms else args.query
    questions = [
        f"1. 用一句人话解释：{main_term} 是什么？",
        f"2. {main_term} 解决什么问题？它不解决什么问题？",
        f"3. 如果你是 AI 产品经理，会用哪些指标判断 {main_term} 做得好不好？",
        f"4. 这个能力属于产品系统的哪一层？为什么？",
        f"5. 请给一个目标公司/业务场景里的应用例子。",
    ]
    print("\n".join(questions[: max(1, args.count)]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

