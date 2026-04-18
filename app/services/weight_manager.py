"""
가중치 관리 모듈

중량 / 부위 / 보관방식별 기본 가중치를 정의하고,
UI에서 사용자 정의 값을 오버라이드할 수 있도록 지원합니다.

규칙:
- 모든 미등록 키워드는 1.0(기본값) 적용
- 가중치는 양수여야 합니다
"""

from dataclasses import dataclass, field
from typing import Dict


DEFAULT_WEIGHT_MAP: Dict[str, float] = {
    "1kg": 1.0,
    "500g": 0.5,
    "200g": 0.2,
}

DEFAULT_PART_MAP: Dict[str, float] = {
    "닭가슴살": 1.0,
    "닭안심": 1.2,
    "닭다리살": 1.0,
    "닭목살": 1.0,
    "닭날개": 0.9,
    "닭발": 0.8,
    "닭볶음탕": 1.1,
}

DEFAULT_STORAGE_MAP: Dict[str, float] = {
    "냉장": 1.0,
    "냉동": 0.95,
    "상온": 0.9,
}

_FALLBACK = 1.0


@dataclass
class WeightConfig:
    """사용자 설정 가능한 가중치 테이블"""
    weight_map: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHT_MAP))
    part_map: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_PART_MAP))
    storage_map: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_STORAGE_MAP))

    def get_weight(self, key: str | None) -> float:
        """중량 가중치 반환. 미등록이면 1.0"""
        if key is None:
            return _FALLBACK
        return self.weight_map.get(key, _FALLBACK)

    def get_part(self, key: str | None) -> float:
        """부위 가중치 반환. 미등록이면 1.0"""
        if key is None:
            return _FALLBACK
        return self.part_map.get(key, _FALLBACK)

    def get_storage(self, key: str | None) -> float:
        """보관방식 가중치 반환. 미등록이면 1.0"""
        if key is None:
            return _FALLBACK
        return self.storage_map.get(key, _FALLBACK)

    def update(
        self,
        weight_map: Dict[str, float] | None = None,
        part_map: Dict[str, float] | None = None,
        storage_map: Dict[str, float] | None = None,
    ) -> None:
        """가중치 테이블을 부분 업데이트합니다."""
        if weight_map:
            for k, v in weight_map.items():
                if v <= 0:
                    raise ValueError(f"가중치는 양수여야 합니다: {k}={v}")
            self.weight_map.update(weight_map)
        if part_map:
            for k, v in part_map.items():
                if v <= 0:
                    raise ValueError(f"가중치는 양수여야 합니다: {k}={v}")
            self.part_map.update(part_map)
        if storage_map:
            for k, v in storage_map.items():
                if v <= 0:
                    raise ValueError(f"가중치는 양수여야 합니다: {k}={v}")
            self.storage_map.update(storage_map)
