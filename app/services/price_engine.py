"""
가격 계산 엔진

공식: P_option = P_base × W_weight × W_part × W_storage

규칙:
- 옵션가가 0이면 기준가(P_base)를 그대로 사용
- 나머지는 기준가를 바탕으로 재계산 (기존 옵션가 무시)
- 결과는 정수로 반올림
- 모든 계산은 명확한 규칙 기반으로 처리하며 추측 로직을 사용하지 않음
"""

import logging
import math
from typing import List

from app.services.parser import parse_option_name, OptionAttributes
from app.services.weight_manager import WeightConfig
from app.models.product_model import OptionItem, CalculatedOption

logger = logging.getLogger(__name__)


def calculate_option_price(
    base_price: int,
    option: OptionItem,
    config: WeightConfig,
) -> CalculatedOption:
    """
    단일 옵션의 변경 가격을 계산합니다.

    Args:
        base_price: 기준 상품 가격 (사용자 입력 또는 판매가)
        option: 옵션 정보
        config: 가중치 설정

    Returns:
        CalculatedOption (기존가 + 변경가 포함)
    """
    attrs: OptionAttributes = parse_option_name(option.option_name)

    w_weight = config.get_weight(attrs.weight)
    w_part = config.get_part(attrs.part)
    w_storage = config.get_storage(attrs.storage)

    new_price = round(base_price * w_weight * w_part * w_storage)

    logger.debug(
        "[계산] %r → 기준가=%d × 중량(%s)=%.2f × 부위(%s)=%.2f × 보관(%s)=%.2f = %d",
        option.option_name,
        base_price,
        attrs.weight, w_weight,
        attrs.part, w_part,
        attrs.storage, w_storage,
        new_price,
    )

    return CalculatedOption(
        option_id=option.option_id,
        option_name=option.option_name,
        original_price=option.option_price,
        calculated_price=new_price,
        stock=option.stock,
        weight=attrs.weight,
        part=attrs.part,
        storage=attrs.storage,
    )


def calculate_all_options(
    base_price: int,
    options: List[OptionItem],
    config: WeightConfig,
) -> List[CalculatedOption]:
    """
    모든 옵션에 대해 가격을 일괄 계산합니다.

    Args:
        base_price: 기준 상품 가격
        options: 옵션 목록
        config: 가중치 설정

    Returns:
        계산 결과 목록
    """
    results = []
    for option in options:
        try:
            result = calculate_option_price(base_price, option, config)
            results.append(result)
        except Exception as exc:
            logger.error("옵션 계산 오류 [%s]: %s", option.option_name, exc)
    return results
