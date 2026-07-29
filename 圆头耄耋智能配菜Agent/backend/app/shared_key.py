from pathlib import Path
from typing import Optional


SHARED_KEY_PATH = Path(__file__).resolve().parents[1] / "data" / ".kimi-key"


def read_shared_key() -> Optional[str]:
    try:
        value = SHARED_KEY_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return value or None
