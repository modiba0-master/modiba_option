"""
상품 검색 및 조회 라우터

조회 전용 엔드포인트만 포함합니다.
가격 수정·자동반영·외부 전송 기능은 절대 구현하지 않습니다.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query

from app.models.product_model import ProductInfo, SearchRequest
from app.services import naver_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["상품 조회"])


@router.get("/search", response_model=List[ProductInfo], summary="상품 검색")
async def search_products(
    query: str = Query(..., description="상품ID 또는 상품명 키워드"),
):
    """
    상품명 또는 상품ID로 네이버 커머스에서 상품을 검색합니다.
    조회 전용이며, 어떠한 데이터도 수정하지 않습니다.
    """
    if not query.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해 주세요.")

    results = await naver_api.search_products(query.strip())
    return results


@router.get("/{product_id}", response_model=ProductInfo, summary="상품 상세 조회")
async def get_product(product_id: str):
    """
    특정 상품의 상세 정보와 옵션 목록을 조회합니다.
    조회 전용이며, 어떠한 데이터도 수정하지 않습니다.
    """
    product = await naver_api.get_product_detail(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {product_id}")
    return product
