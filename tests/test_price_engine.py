"""
가격 계산 엔진 테스트

Harness First 원칙: 기능 구현 전에 테스트를 먼저 작성합니다.
공식: P_option = P_base × W_weight × W_part × W_storage
결과는 정수 반올림 처리.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.product_model import OptionItem
from app.services.weight_manager import WeightConfig
from app.services.price_engine import calculate_option_price, calculate_all_options


def make_option(name: str, price: int = 0, stock: int = 100) -> OptionItem:
    return OptionItem(option_id="TEST", option_name=name, option_price=price, stock=stock)


@pytest.fixture
def default_config() -> WeightConfig:
    return WeightConfig()


class TestBasicCalculation:
    """기본 계산 로직 테스트"""

    def test_닭가슴살_1kg_냉동(self, default_config):
        """1.0 × 1.0 × 0.95 = 0.95 → 14250"""
        option = make_option("닭가슴살 1kg 냉동")
        result = calculate_option_price(15000, option, default_config)
        assert result.calculated_price == round(15000 * 1.0 * 1.0 * 0.95)

    def test_닭안심_500g_냉동(self, default_config):
        """0.5 × 1.2 × 0.95 = 0.57 → 8550"""
        option = make_option("닭안심 500g 냉동")
        result = calculate_option_price(15000, option, default_config)
        assert result.calculated_price == round(15000 * 0.5 * 1.2 * 0.95)

    def test_닭다리살_200g_냉장(self, default_config):
        """0.2 × 1.0 × 1.0 = 0.2 → 3000"""
        option = make_option("닭다리살 200g 냉장")
        result = calculate_option_price(15000, option, default_config)
        assert result.calculated_price == round(15000 * 0.2 * 1.0 * 1.0)

    def test_닭가슴살_500g_냉장(self, default_config):
        """0.5 × 1.0 × 1.0 = 0.5 → 7500"""
        option = make_option("닭가슴살 500g 냉장")
        result = calculate_option_price(15000, option, default_config)
        assert result.calculated_price == round(15000 * 0.5 * 1.0 * 1.0)


class TestFallbackBehavior:
    """미등록 키워드 폴백 테스트"""

    def test_unknown_weight_uses_1_0(self, default_config):
        """미등록 중량 → 1.0 적용"""
        option = make_option("닭가슴살 300g 냉동")
        result = calculate_option_price(10000, option, default_config)
        # 300g은 미등록 → weight=1.0, 부위=닭가슴살=1.0, 냉동=0.95
        assert result.calculated_price == round(10000 * 1.0 * 1.0 * 0.95)

    def test_unknown_part_uses_1_0(self, default_config):
        """미등록 부위 → 1.0 적용"""
        option = make_option("혼합구성 500g 냉동")
        result = calculate_option_price(10000, option, default_config)
        assert result.calculated_price == round(10000 * 0.5 * 1.0 * 0.95)

    def test_unknown_storage_uses_1_0(self, default_config):
        """미등록 보관방식 → 1.0 적용"""
        option = make_option("닭가슴살 500g 실온")
        result = calculate_option_price(10000, option, default_config)
        assert result.calculated_price == round(10000 * 0.5 * 1.0 * 1.0)

    def test_all_unknown_returns_base_price(self, default_config):
        """모든 속성 미인식 → 기준가 그대로"""
        option = make_option("혼합구성 특가세트")
        result = calculate_option_price(10000, option, default_config)
        assert result.calculated_price == 10000


class TestRounding:
    """정수 반올림 테스트"""

    def test_result_is_integer(self, default_config):
        option = make_option("닭안심 500g 냉동")
        result = calculate_option_price(13000, option, default_config)
        assert isinstance(result.calculated_price, int)

    def test_rounding_behavior(self, default_config):
        """13000 × 0.5 × 1.2 × 0.95 = 7410.0 → 7410"""
        option = make_option("닭안심 500g 냉동")
        result = calculate_option_price(13000, option, default_config)
        assert result.calculated_price == round(13000 * 0.5 * 1.2 * 0.95)


class TestOriginalPricePreserved:
    """기존 옵션가가 결과에 보존되는지 테스트"""

    def test_original_price_preserved(self, default_config):
        option = make_option("닭가슴살 500g 냉동", price=500)
        result = calculate_option_price(10000, option, default_config)
        assert result.original_price == 500
        assert result.calculated_price != 500  # 재계산된 값

    def test_zero_original_price_still_recalculated(self, default_config):
        """옵션가 0도 재계산 수행"""
        option = make_option("닭가슴살 500g 냉장", price=0)
        result = calculate_option_price(10000, option, default_config)
        assert result.original_price == 0
        assert result.calculated_price == round(10000 * 0.5 * 1.0 * 1.0)


class TestCustomWeightConfig:
    """사용자 정의 가중치 테스트"""

    def test_custom_weight_map(self):
        config = WeightConfig()
        config.update(weight_map={"500g": 0.6})
        option = make_option("닭가슴살 500g 냉장")
        result = calculate_option_price(10000, option, config)
        assert result.calculated_price == round(10000 * 0.6 * 1.0 * 1.0)

    def test_custom_part_map(self):
        config = WeightConfig()
        config.update(part_map={"닭가슴살": 1.5})
        option = make_option("닭가슴살 1kg 냉장")
        result = calculate_option_price(10000, option, config)
        assert result.calculated_price == round(10000 * 1.0 * 1.5 * 1.0)

    def test_invalid_weight_raises(self):
        config = WeightConfig()
        with pytest.raises(ValueError):
            config.update(weight_map={"500g": -0.1})


class TestBatchCalculation:
    """일괄 계산 테스트"""

    def test_calculate_all_options(self, default_config):
        options = [
            make_option("닭가슴살 1kg 냉동"),
            make_option("닭안심 500g 냉동"),
            make_option("닭다리살 200g 냉장"),
        ]
        results = calculate_all_options(15000, options, default_config)
        assert len(results) == 3

    def test_each_result_has_correct_option_id(self, default_config):
        options = [
            OptionItem(option_id="A", option_name="닭가슴살 1kg 냉동", option_price=0, stock=10),
            OptionItem(option_id="B", option_name="닭안심 500g 냉동", option_price=0, stock=20),
        ]
        results = calculate_all_options(10000, options, default_config)
        assert results[0].option_id == "A"
        assert results[1].option_id == "B"
