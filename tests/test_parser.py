"""
옵션명 파서 테스트

Harness First 원칙: 기능 구현 전에 테스트를 먼저 작성합니다.
모든 테스트는 명확한 입력/출력 기반으로 작성합니다.
"""

import pytest
import sys
import os

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.parser import parse_option_name, OptionAttributes


class TestWeightParsing:
    """중량 추출 테스트"""

    def test_gram_extraction(self):
        result = parse_option_name("닭안심 500g 냉동")
        assert result.weight == "500g"

    def test_kilogram_extraction(self):
        result = parse_option_name("닭가슴살 1kg 냉장")
        assert result.weight == "1kg"

    def test_200g_extraction(self):
        result = parse_option_name("닭다리살 200g 냉동")
        assert result.weight == "200g"

    def test_weight_with_space(self):
        """숫자와 단위 사이 공백 허용"""
        result = parse_option_name("닭가슴살 1 kg 냉동")
        assert result.weight == "1kg"

    def test_decimal_weight(self):
        """소수점 중량 (예: 1.5kg)"""
        result = parse_option_name("닭가슴살 1.5kg 냉동")
        assert result.weight == "1.5kg"

    def test_no_weight_returns_none(self):
        """중량 정보 없으면 None 반환"""
        result = parse_option_name("닭가슴살 냉동")
        assert result.weight is None

    def test_weight_only_option(self):
        result = parse_option_name("500g")
        assert result.weight == "500g"


class TestPartParsing:
    """부위 추출 테스트"""

    def test_닭가슴살(self):
        result = parse_option_name("닭가슴살 500g 냉동")
        assert result.part == "닭가슴살"

    def test_닭안심(self):
        result = parse_option_name("닭안심 500g 냉동")
        assert result.part == "닭안심"

    def test_닭다리살(self):
        result = parse_option_name("닭다리살 200g 냉장")
        assert result.part == "닭다리살"

    def test_no_part_returns_none(self):
        result = parse_option_name("500g 냉동")
        assert result.part is None

    def test_longer_keyword_priority(self):
        """긴 키워드(닭가슴살)가 짧은 키워드보다 우선 매칭되어야 함"""
        result = parse_option_name("닭가슴살 500g")
        assert result.part == "닭가슴살"


class TestStorageParsing:
    """보관방식 추출 테스트"""

    def test_냉동(self):
        result = parse_option_name("닭안심 500g 냉동")
        assert result.storage == "냉동"

    def test_냉장(self):
        result = parse_option_name("닭가슴살 1kg 냉장")
        assert result.storage == "냉장"

    def test_상온(self):
        result = parse_option_name("닭볶음탕 500g 상온")
        assert result.storage == "상온"

    def test_no_storage_returns_none(self):
        result = parse_option_name("닭가슴살 500g")
        assert result.storage is None


class TestFullOptionName:
    """전체 옵션명 파싱 통합 테스트"""

    def test_standard_option(self):
        result = parse_option_name("닭안심 500g 냉동")
        assert result.weight == "500g"
        assert result.part == "닭안심"
        assert result.storage == "냉동"

    def test_reordered_option(self):
        """순서가 달라도 올바르게 추출"""
        result = parse_option_name("냉동 닭가슴살 1kg")
        assert result.weight == "1kg"
        assert result.part == "닭가슴살"
        assert result.storage == "냉동"

    def test_raw_preserved(self):
        """원본 문자열이 raw에 보존되어야 함"""
        text = "닭안심 500g 냉동"
        result = parse_option_name(text)
        assert result.raw == text

    def test_empty_string(self):
        result = parse_option_name("")
        assert result.weight is None
        assert result.part is None
        assert result.storage is None

    def test_invalid_type_returns_default(self):
        result = parse_option_name(None)
        assert result.weight is None

    def test_all_none_unknown_option(self):
        """완전히 알 수 없는 옵션명"""
        result = parse_option_name("혼합구성 특가세트")
        assert result.weight is None
        assert result.part is None
        assert result.storage is None
