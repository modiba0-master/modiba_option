"""
네이버 커머스 API 연동 모듈 (v2)

조회(GET) 전용입니다. 가격 수정·자동반영·외부전송은 절대 구현하지 않습니다.

환경변수:
  NAVER_COMMERCE_API_CLIENT_ID     - 네이버 커머스 API 클라이언트 ID
  NAVER_COMMERCE_API_CLIENT_SECRET - 네이버 커머스 API 클라이언트 시크릿 (bcrypt salt)

인증 방식:
  bcrypt(password="{client_id}_{timestamp}", salt=client_secret) → Base64
  POST /external/v1/oauth2/token → Bearer Token
  토큰은 세션 내 메모리에만 캐시하며 외부 저장 없음.

API 버전:
  v2 (v1은 2022년 12월 서비스 종료)
  - 채널상품 조회: GET /v2/products/channel-products/{channelProductNo}
  - 원상품 조회:   GET /v2/products/origin-products/{originProductNo}
  - 상품 목록:     GET /v2/products?...
"""

import logging
import os
import time
import base64
from typing import List, Optional

import bcrypt
import httpx

from app.models.product_model import OptionItem, ProductInfo

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.commerce.naver.com/external"
_TOKEN_URL = f"{_BASE_URL}/v1/oauth2/token"

# 런타임 토큰 캐시 (메모리 전용)
_token_cache: dict = {"access_token": "", "expires_at": 0}


# ──────────────────────────────────────────────
# 인증
# ──────────────────────────────────────────────

def _get_client_credentials() -> tuple[str, str]:
    client_id = os.getenv("NAVER_COMMERCE_API_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_COMMERCE_API_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("NAVER_COMMERCE_API_CLIENT_ID / SECRET 환경변수가 설정되지 않았습니다.")
    return client_id, client_secret


def _make_signature(client_id: str, client_secret: str, timestamp: int) -> str:
    """
    네이버 커머스 API 전자서명 생성
    bcrypt.hashpw(password="{client_id}_{timestamp}", salt=client_secret) → Base64
    """
    password = f"{client_id}_{timestamp}"
    hashed = bcrypt.hashpw(password.encode("utf-8"), client_secret.encode("utf-8"))
    return base64.b64encode(hashed).decode("utf-8")


async def _fetch_access_token() -> str:
    """OAuth2 Client Credentials 방식으로 액세스 토큰을 발급받습니다."""
    client_id, client_secret = _get_client_credentials()
    if not client_id:
        return ""

    timestamp = int(time.time() * 1000)
    signature = _make_signature(client_id, client_secret, timestamp)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": client_id,
                    "timestamp": timestamp,
                    "client_secret_sign": signature,
                    "grant_type": "client_credentials",
                    "type": "SELF",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token", "")
            expires_in = int(data.get("expires_in", 3600))
            _token_cache["access_token"] = token
            _token_cache["expires_at"] = time.time() + expires_in - 60
            logger.info("네이버 커머스 API 토큰 발급 완료 (유효 %d초)", expires_in)
            return token
    except Exception as exc:
        logger.error("토큰 발급 오류: %s", exc)
        return ""


async def _get_headers() -> dict:
    """유효한 Bearer 토큰을 포함한 헤더를 반환합니다."""
    now = time.time()
    if not _token_cache["access_token"] or now >= _token_cache["expires_at"]:
        await _fetch_access_token()
    token = _token_cache.get("access_token", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

async def search_products(query: str) -> List[ProductInfo]:
    """
    상품ID(채널상품번호 또는 원상품번호)로 상품을 조회합니다.
    숫자 ID이면 채널상품 → 원상품 순으로 시도합니다.
    """
    query = query.strip()

    # 숫자 ID면 상세 직접 조회
    if query.isdigit():
        product = await get_product_detail(query)
        if product:
            return [product]
        return []

    # 키워드 검색 (v2 목록 API)
    url = f"{_BASE_URL}/v2/products"
    params = {"searchKeyword": query, "size": 20, "page": 1}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=await _get_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("contents", data.get("items", []))
            result = [_map_channel_product(it) for it in items]
            return [r for r in result if r]
    except Exception as exc:
        logger.error("상품 검색 오류: %s", exc)
        return _mock_search(query)


async def get_product_detail(product_id: str) -> Optional[ProductInfo]:
    """
    상품 상세 정보를 조회합니다.
    채널상품번호 우선 시도 → 실패 시 원상품번호로 재시도
    """
    # 1) 채널상품 조회
    product = await _get_channel_product(product_id)
    if product:
        return product

    # 2) 원상품 조회
    product = await _get_origin_product(product_id)
    if product:
        return product

    logger.warning("상품 조회 실패, 목 데이터 반환: %s", product_id)
    return _mock_product(product_id)


async def _get_channel_product(channel_product_no: str) -> Optional[ProductInfo]:
    """채널상품번호로 상품 조회 (v2)"""
    url = f"{_BASE_URL}/v2/products/channel-products/{channel_product_no}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=await _get_headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return _map_channel_product(data)
    except httpx.HTTPStatusError as exc:
        logger.debug("채널상품 조회 실패 (%s): %s", channel_product_no, exc.response.status_code)
        return None
    except Exception as exc:
        logger.error("채널상품 조회 오류: %s", exc)
        return None


async def _get_origin_product(origin_product_no: str) -> Optional[ProductInfo]:
    """원상품번호로 상품 조회 (v2)"""
    url = f"{_BASE_URL}/v2/products/origin-products/{origin_product_no}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=await _get_headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return _map_origin_product(data)
    except httpx.HTTPStatusError as exc:
        logger.debug("원상품 조회 실패 (%s): %s", origin_product_no, exc.response.status_code)
        return None
    except Exception as exc:
        logger.error("원상품 조회 오류: %s", exc)
        return None


# ──────────────────────────────────────────────
# 응답 파서 (v2 스펙)
# ──────────────────────────────────────────────

def _map_channel_product(data: dict) -> Optional[ProductInfo]:
    """채널상품 응답 → ProductInfo 변환"""
    try:
        channel_no = str(data.get("channelProductNo", data.get("id", "")))
        origin = data.get("originProduct", {})
        product_name = origin.get("name", data.get("name", ""))
        sale_price = int(origin.get("salePrice", data.get("salePrice", 0)) or 0)

        # 할인
        discount_info = origin.get("detailAttribute", {}).get("optionInfo", {})
        discount_amount = int(origin.get("customerBenefit", {})
                              .get("immediateDiscountPolicy", {})
                              .get("discountMethod", {})
                              .get("value", 0) or 0)

        # 옵션
        option_info = origin.get("detailAttribute", {}).get("optionInfo", {})
        options = _parse_options(option_info)

        # 옵션이 없으면 채널 옵션 시도
        if not options:
            options = _parse_options(data.get("detailAttribute", {}).get("optionInfo", {}))

        return ProductInfo(
            product_id=channel_no,
            product_name=product_name,
            sale_price=sale_price,
            discount_amount=discount_amount,
            options=options,
        )
    except Exception as exc:
        logger.error("채널상품 파싱 오류: %s | 데이터: %s", exc, str(data)[:200])
        return None


def _map_origin_product(data: dict) -> Optional[ProductInfo]:
    """원상품 응답 → ProductInfo 변환"""
    try:
        origin = data.get("originProduct", data)
        origin_no = str(origin.get("id", data.get("id", "")))
        product_name = origin.get("name", "")
        sale_price = int(origin.get("salePrice", 0) or 0)

        discount_amount = int(origin.get("customerBenefit", {})
                              .get("immediateDiscountPolicy", {})
                              .get("discountMethod", {})
                              .get("value", 0) or 0)

        option_info = origin.get("detailAttribute", {}).get("optionInfo", {})
        options = _parse_options(option_info)

        return ProductInfo(
            product_id=origin_no,
            product_name=product_name,
            sale_price=sale_price,
            discount_amount=discount_amount,
            options=options,
        )
    except Exception as exc:
        logger.error("원상품 파싱 오류: %s | 데이터: %s", exc, str(data)[:200])
        return None


def _parse_options(option_info: dict) -> List[OptionItem]:
    """옵션 정보 파싱 — v2 응답 구조 기반"""
    options: List[OptionItem] = []
    if not option_info:
        return options

    option_combinations = option_info.get("optionCombinations", [])
    for combo in option_combinations:
        option_name_parts = []
        for key in ("optionName1", "optionName2", "optionName3", "optionName4"):
            val = combo.get(key, "")
            if val:
                option_name_parts.append(val)
        option_name = " ".join(option_name_parts) or combo.get("optionName", "")
        options.append(OptionItem(
            option_id=str(combo.get("id", combo.get("optionCombinationNo", ""))),
            option_name=option_name,
            option_price=int(combo.get("price", combo.get("optionPrice", 0)) or 0),
            stock=int(combo.get("stockQuantity", 0) or 0),
        ))

    # optionCombinations 없으면 단일 옵션 목록 시도
    if not options:
        for opt in option_info.get("options", []):
            options.append(OptionItem(
                option_id=str(opt.get("id", "")),
                option_name=opt.get("name", opt.get("optionName", "")),
                option_price=int(opt.get("price", 0) or 0),
                stock=int(opt.get("stockQuantity", 0) or 0),
            ))

    return options


# ──────────────────────────────────────────────
# 개발/테스트용 목(mock) 데이터
# ──────────────────────────────────────────────

def _mock_search(query: str) -> List[ProductInfo]:
    logger.info("목 데이터로 검색 결과를 반환합니다: %r", query)
    return [_mock_product(query)]


def _mock_product(product_id: str) -> ProductInfo:
    return ProductInfo(
        product_id=product_id,
        product_name=f"[목데이터] 닭가슴살 모음 ({product_id})",
        sale_price=15000,
        discount_amount=1000,
        options=[
            OptionItem(option_id="OPT001", option_name="닭가슴살 1kg 냉동", option_price=0, stock=100),
            OptionItem(option_id="OPT002", option_name="닭안심 500g 냉동", option_price=0, stock=80),
            OptionItem(option_id="OPT003", option_name="닭다리살 200g 냉장", option_price=0, stock=50),
            OptionItem(option_id="OPT004", option_name="닭가슴살 500g 냉장", option_price=500, stock=60),
        ],
    )
