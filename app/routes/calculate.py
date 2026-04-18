"""
가격 계산 라우터

옵션 가격 재계산 결과를 반환합니다.
엑셀 다운로드 엔드포인트도 포함됩니다.

⚠️ 이 라우터는 계산 결과 반환 전용입니다.
   네이버 API로 가격을 반영하는 코드는 절대 작성하지 않습니다.
"""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import io

from app.models.product_model import CalculateRequest, CalculationResult
from app.services import naver_api
from app.services.price_engine import calculate_all_options
from app.services.weight_manager import WeightConfig
from app.services.excel_exporter import build_excel_bytes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calculate", tags=["가격 계산"])


@router.post("/", response_model=CalculationResult, summary="옵션 가격 계산")
async def calculate_prices(req: CalculateRequest):
    """
    기준가와 가중치를 기반으로 모든 옵션 가격을 재계산합니다.
    결과는 조회 전용이며, 네이버 서버에 반영되지 않습니다.
    """
    product = await naver_api.get_product_detail(req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {req.product_id}")

    config = WeightConfig()
    try:
        config.update(
            weight_map=req.weight_map,
            part_map=req.part_map,
            storage_map=req.storage_map,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    calculated_options = calculate_all_options(req.base_price, product.options, config)

    return CalculationResult(
        product_id=product.product_id,
        product_name=product.product_name,
        sale_price=product.sale_price,
        discount_amount=product.discount_amount,
        discounted_price=product.discounted_price,
        base_price_used=req.base_price,
        options=calculated_options,
    )


@router.post("/download-excel", summary="계산 결과 엑셀 다운로드")
async def download_excel(req: CalculateRequest):
    """
    계산 결과를 엑셀 파일로 다운로드합니다.
    파일은 서버에 저장되지 않으며, 스트리밍으로 즉시 반환됩니다.
    """
    product = await naver_api.get_product_detail(req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없습니다: {req.product_id}")

    config = WeightConfig()
    try:
        config.update(
            weight_map=req.weight_map,
            part_map=req.part_map,
            storage_map=req.storage_map,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    calculated_options = calculate_all_options(req.base_price, product.options, config)
    result = CalculationResult(
        product_id=product.product_id,
        product_name=product.product_name,
        sale_price=product.sale_price,
        discount_amount=product.discount_amount,
        discounted_price=product.discounted_price,
        base_price_used=req.base_price,
        options=calculated_options,
    )

    excel_bytes = build_excel_bytes(result)
    filename = f"option_price_{product.product_id}.xlsx"

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
