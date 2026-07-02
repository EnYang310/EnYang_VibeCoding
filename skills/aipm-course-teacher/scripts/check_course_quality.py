#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COURSES = ROOT / "references" / "courses"


REQUIRED_PATTERNS = {
    "scope/correction": [r"纠偏", r"是什么", r"不是什么", r"scope"],
    "overview": [r"一页纸", r"总览", r"overview"],
    "history": [r"前因后果", r"为什么", r"历史", r"出现"],
    "glossary": [r"基础词汇", r"术语", r"glossary"],
    "mechanism": [r"机制", r"架构", r"workflow", r"流程"],
    "pm framework": [r"PM", r"产品经理", r"判断框架", r"指标"],
    "project path": [r"项目", r"实战", r"PRD", r"MVP"],
    "interview": [r"面试", r"高频问答", r"follow-up", r"追问"],
    "exercises": [r"练习", r"作业", r"小测", r"exercise"],
    "source digest": [r"来源", r"官方文档", r"GitHub", r"论文", r"精读"],
    "source audit": [r"来源审计", r"观点分级", r"事实", r"课程归纳"],
}

LEVELS = {
    "mini": {
        "min_chars": 20000,
        "min_headings": 18,
        "min_urls": 5,
        "min_authority_urls": 2,
        "min_github_urls": 1,
    },
    "standard": {
        "min_chars": 80000,
        "min_headings": 120,
        "min_urls": 80,
        "min_authority_urls": 40,
        "min_github_urls": 30,
    },
    "harness": {
        "min_chars": 87000,
        "min_headings": 200,
        "min_urls": 200,
        "min_authority_urls": 100,
        "min_github_urls": 60,
    },
}

AUTHORITY_URL_PATTERNS = [
    r"openai\.com",
    r"openai\.github\.io",
    r"github\.com/openai",
    r"anthropic\.com",
    r"docs\.anthropic\.com",
    r"platform\.claude\.com",
    r"github\.com/anthropics",
    r"deepseek\.com",
    r"api-docs\.deepseek\.com",
    r"github\.com/deepseek-ai",
    r"docs\.github\.com",
    r"github\.com/github",
    r"learn\.microsoft\.com",
    r"github\.com/microsoft",
    r"developers\.google\.com",
    r"ai\.google\.dev",
    r"cloud\.google\.com",
    r"aws\.amazon\.com",
    r"docs\.aws\.amazon\.com",
    r"ai\.meta\.com",
    r"github\.com/facebookresearch",
    r"cloudflare\.com",
    r"modelcontextprotocol\.io",
    r"github\.com/modelcontextprotocol",
    r"agentskills\.io",
    r"arxiv\.org",
]

GITHUB_PROJECT_PATTERN = r"https?://github\.com/[^/\s)>\"]+/[^/\s)>\"]+"


def course_path(course_id: str) -> Path:
    return COURSES / course_id / "course.md"


def count_urls(text: str) -> int:
    return len(re.findall(r"https?://[^\s)>\"]+", text))

def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)>\"]+", text)


def count_authority_urls(urls: list[str]) -> int:
    count = 0
    for url in urls:
        if any(re.search(pattern, url, flags=re.IGNORECASE) for pattern in AUTHORITY_URL_PATTERNS):
            count += 1
    return count


def count_github_project_urls(text: str) -> int:
    return len(re.findall(GITHUB_PROJECT_PATTERN, text, flags=re.IGNORECASE))


def count_headings(text: str) -> int:
    return len(re.findall(r"^#{2,6}\s+", text, flags=re.MULTILINE))


def check_patterns(text: str) -> list[str]:
    missing: list[str] = []
    for name, patterns in REQUIRED_PATTERNS.items():
        if not any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            missing.append(name)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether an AI PM course is substantial enough to register.")
    parser.add_argument("--course", required=True, help="Course id under references/courses/<course-id>/")
    parser.add_argument("--level", choices=sorted(LEVELS), default="standard")
    parser.add_argument("--min-chars", type=int)
    parser.add_argument("--min-headings", type=int)
    parser.add_argument("--min-urls", type=int)
    args = parser.parse_args()

    level_defaults = LEVELS[args.level]
    min_chars = args.min_chars or level_defaults["min_chars"]
    min_headings = args.min_headings or level_defaults["min_headings"]
    min_urls = args.min_urls or level_defaults["min_urls"]
    min_authority_urls = level_defaults["min_authority_urls"]
    min_github_urls = level_defaults["min_github_urls"]

    path = course_path(args.course)
    if not path.exists():
        print(f"FAIL course file not found: {path}")
        return 1

    text = path.read_text(encoding="utf-8")
    urls = extract_urls(text)
    char_count = len(text)
    heading_count = count_headings(text)
    url_count = len(urls)
    authority_url_count = count_authority_urls(urls)
    github_url_count = count_github_project_urls(text)
    missing = check_patterns(text)

    failures: list[str] = []
    if char_count < min_chars:
        failures.append(f"too short: {char_count} chars < {min_chars}")
    if heading_count < min_headings:
        failures.append(f"too few sections: {heading_count} headings < {min_headings}")
    if url_count < min_urls:
        failures.append(f"too few source links: {url_count} urls < {min_urls}")
    if authority_url_count < min_authority_urls:
        failures.append(f"too few authority links: {authority_url_count} urls < {min_authority_urls}")
    if github_url_count < min_github_urls:
        failures.append(f"too few GitHub project links: {github_url_count} urls < {min_github_urls}")
    if not re.search(r"重要链接精读|链接精读|来源精读", text):
        failures.append("missing source digestion section: 重要链接精读/来源精读")
    if not re.search(r"来源审计|观点分级", text):
        failures.append("missing source audit section: 来源审计/观点分级")
    if missing:
        failures.append("missing required areas: " + ", ".join(missing))

    print(f"course={args.course}")
    print(f"level={args.level}")
    print(f"chars={char_count}")
    print(f"headings={heading_count}")
    print(f"urls={url_count}")
    print(f"authority_urls={authority_url_count}")
    print(f"github_urls={github_url_count}")

    if failures:
        print("STATUS=FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
