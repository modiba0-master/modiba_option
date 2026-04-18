"""
데이터 모델 정의

Pydantic v2 기반 모델로 API 입출력 및 내부 데이터 전달에 사용합니다.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class OptionItem(BaseModel):
    """옵션 단위 정보 (API 응답 기준)"""
    option_id: str = Field(..., description="옵션 ID")
    option_name: str = Field(..., description="옵션명 (예: 닭안심 500g 냉동)")
    option_price: int = Field(0, description="기존 옵션가 (0이면 기준가 적용)")
    stock: int = Field(0, description="재고 수량")


class ProductInfo(BaseModel):
    """상품 기본 정보"""
    product_id: str = Field(..., description="상품 ID")
    product_name: str = Field(..., description="상품명")
    sale_price: int = Field(..., description="판매가")
    discount_amount: int = Field(0, description="기본할인 금액")
    options: List[OptionItem] = Field(default_factory=list, description="옵션 목록")

    @property
    def discounted_price(self) -> int:
        """할인가 = 판매가 - 기본할인"""
        return max(0, self.sale_price - self.discount_amount)


class CalculatedOption(BaseModel):
    """가격 계산 결과 (옵션 단위)"""
    option_id: str
    option_name: str
    original_price: int = Field(..., description="기존 옵션가")
    calculated_price: int = Field(..., description="변경 옵션가 (재계산)")
    stock: int
    weight: Optional[str] = None
    part: Optional[str] = None
    storage: Optional[str] = None


class CalculationResult(BaseModel):
    """전체 계산 결과 (상품 단위)"""
    product_id: str
    product_name: str
    sale_price: int
    discount_amount: int
    discounted_price: int
    base_price_used: int = Field(..., description="계산에 사용된 기준가")
    options: List[CalculatedOption]


class SearchRequest(BaseModel):
    """상품 검색 요청"""
    query: str = Field(..., description="상품ID 또는 상품명")


class CalculateRequest(BaseModel):
    """가격 계산 요청"""
    product_id: str
    base_price: int = Field(..., gt=0, description="기준가 (양수여야 함)")
    weight_map: Optional[dict] = None
    part_map: Optional[dict] = None
    storage_map: Optional[dict] = None
