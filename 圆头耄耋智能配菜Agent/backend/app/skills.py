from pathlib import Path
from typing import Dict, Iterable


SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"


class SkillNotFoundError(RuntimeError):
    pass


def load_skill(name: str) -> str:
    path = SKILLS_ROOT / name / "SKILL.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise SkillNotFoundError("缺少 Agent Skill：{}".format(name)) from exc


def load_skills(names: Iterable[str]) -> str:
    return "\n\n---\n\n".join(load_skill(name) for name in names)


def skill_versions() -> Dict[str, str]:
    versions: Dict[str, str] = {}
    for path in SKILLS_ROOT.glob("*/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        name = path.parent.name
        version = "unknown"
        for line in text.splitlines():
            if line.startswith("version:"):
                version = line.split(":", 1)[1].strip()
                break
        versions[name] = version
    return versions
