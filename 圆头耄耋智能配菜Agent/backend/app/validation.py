import re
from typing import Iterable


_CJK = re.compile(r"[\u3400-\u9fff]")
_ASCII_LETTER = re.compile(r"[A-Za-z]")


def normalize_identity(value: str) -> str:
    return "".join(value.split()).casefold()


def validate_usda_query(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if _CJK.search(normalized) or not _ASCII_LETTER.search(normalized):
        raise ValueError("nutrition query 必须是英文 USDA 查询词")
    return normalized


def require_unique(values: Iterable[str], field_name: str) -> None:
    normalized = [normalize_identity(value) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} 必须唯一")
