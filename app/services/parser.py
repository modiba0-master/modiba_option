"""
옵션명 파서 모듈

옵션명 문자열을 분석하여 중량 / 부위 / 보관방식 속성을 추출합니다.
정규식 기반으로 동작하며, 인식 실패 시 기본값(1.0에 해당하는 키)을 반환합니다.

규칙:
- 공백·순서 무관 처리
- 부분 문자열 매칭 허용
- 인식 실패 시 기본값(None) 반환
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 중량 패턴: 숫자 + 단위(kg/g)
# ──────────────────────────────────────────────
_WEIGHT_PATTERNS = [
    (re.compile(r"(\d+(?:\.\d+)?)\s*kg", re.IGNORECASE), lambda m: f"{m.group(1)}kg"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*g(?!b)", re.IGNORECASE), lambda m: f"{m.group(1)}g"),
]

# ──────────────────────────────────────────────
# 부위 키워드 (긴 것부터 매칭해야 오인식 방지)
# ──────────────────────────────────────────────
_PART_KEYWORDS = [
    "닭가슴살",
    "닭안심",
    "닭다리살",
    "닭목살",
    "닭날개",
    "닭발",
    "닭볶음탕",
]

# ──────────────────────────────────────────────
# 보관방식 키워드
# ──────────────────────────────────────────────
_STORAGE_KEYWORDS = ["냉동", "냉장", "상온"]


@dataclass
class OptionAttributes:
    """옵션명에서 추출된 속성 정보"""
    weight: Optional[str] = None   # 예: "500g", "1kg"
    part: Optional[str] = None     # 예: "닭안심"
    storage: Optional[str] = None  # 예: "냉동"
    raw: str = ""                  # 원본 옵션명


def parse_option_name(option_name: str) -> OptionAttributes:
    """
    옵션명 문자열을 분석하여 OptionAttributes를 반환합니다.

    Args:
        option_name: 분석할 옵션명 (예: "닭안심 500g 냉동")

    Returns:
        OptionAttributes 인스턴스
    """
    if not isinstance(option_name, str):
        logger.warning("옵션명이 문자열이 아닙니다: %r", option_name)
        return OptionAttributes(raw=str(option_name))

    text = option_name.strip()
    attrs = OptionAttributes(raw=text)

    # 1) 중량 추출
    for pattern, formatter in _WEIGHT_PATTERNS:
        m = pattern.search(text)
        if m:
            attrs.weight = formatter(m)
            break

    # 2) 부위 추출 (긴 키워드 우선)
    for keyword in _PART_KEYWORDS:
        if keyword in text:
            attrs.part = keyword
            break

    # 3) 보관방식 추출
    for keyword in _STORAGE_KEYWORDS:
        if keyword in text:
            attrs.storage = keyword
            break

    if attrs.weight is None:
        logger.debug("중량 인식 실패 → 기본값 적용: %r", text)
    if attrs.part is None:
        logger.debug("부위 인식 실패 → 기본값 적용: %r", text)
    if attrs.storage is None:
        logger.debug("보관방식 인식 실패 → 기본값 적용: %r", text)

    return attrs
