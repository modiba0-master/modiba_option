"""
네이버 커머스 API 연동 모듈

조회(GET) 전용입니다. 가격 수정·자동반영·외부전송은 절대 구현하지 않습니다.

환경변수:
  NAVER_COMMERCE_API_CLIENT_ID     - 네이버 커머스 API 클라이언트 ID
  NAVER_COMMERCE_API_CLIENT_SECRET - 네이버 커머스 API 클라이언트 시크릿

인증 방식:
  Client Credentials Grant (POST /v1/oauth2/token) → Bearer Token
  토큰은 세션 내 메모리에만 캐시하며 외부 저장 없음.
"""

import logging
import os
import time
import hashlib
import hmac
import base64
from typing import List, Optional

import httpx
from app.models.product_model import OptionItem, ProductInfo

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.commerce.naver.com/external"
_TOKEN_URL = "https://api.commerce.naver.com/external/v1/oauth2/token"

# 런타임 토큰 캐시 (메모리 전용)
_token_cache: dict = {"access_token": "", "expires_at": 0}


def _get_client_credentials() -> tuple[str, str]:
    client_id = os.getenv("NAVER_COMMERCE_API_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_COMMERCE_API_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("NAVER_COMMERCE_API_CLIENT_ID / SECRET 환경변수가 설정되지 않았습니다.")
    return client_id, client_secret


def _make_signature(client_id: str, client_secret: str, timestamp: int) -> str:
    """네이버 커머스 API HMAC-SHA256 서명 생성"""
    message = f"{client_id}_{timestamp}"
    signature = hmac.new(
        client_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(signature).decode("utf-8")


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


async def search_products(query: str) -> List[ProductInfo]:
    """
    상품명 또는 상품ID로 상품을 검색합니다. (조회 전용)

    Args:
        query: 상품ID 또는 상품명 키워드

    Returns:
        ProductInfo 목록
    """
    url = f"{_BASE_URL}/v1/products/search"
    params = {"query": query, "limit": 20}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=await _get_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("상품 검색 HTTP 오류: %s", exc)
        return _mock_search(query)
    except Exception as exc:
        logger.error("상품 검색 오류: %s", exc)
        return _mock_search(query)

    return _parse_product_list(data)


async def get_product_detail(product_id: str) -> Optional[ProductInfo]:
    """
    상품 상세 정보와 옵션 목록을 조회합니다. (조회 전용)

    Args:
        product_id: 네이버 상품 ID

    Returns:
        ProductInfo 또는 None
    """
    url = f"{_BASE_URL}/v1/products/{product_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=await _get_headers())
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("상품 상세 조회 HTTP 오류: %s", exc)
        return _mock_product(product_id)
    except Exception as exc:
        logger.error("상품 상세 조회 오류: %s", exc)
        return _mock_product(product_id)

    return _parse_product_detail(data)


# ──────────────────────────────────────────────
# 내부 파서
# ──────────────────────────────────────────────

def _parse_product_list(data: dict) -> List[ProductInfo]:
    items = data.get("items", [])
    result = []
    for item in items:
        try:
            result.append(_map_product(item))
        except Exception as exc:
            logger.warning("상품 파싱 실패: %s", exc)
    return result


def _parse_product_detail(data: dict) -> Optional[ProductInfo]:
    try:
        return _map_product(data)
    except Exception as exc:
        logger.error("상품 상세 파싱 실패: %s", exc)
        return None


def _map_product(item: dict) -> ProductInfo:
    options_raw = item.get("options", [])
    options = [
        OptionItem(
            option_id=str(opt.get("optionId", "")),
            option_name=opt.get("optionName", ""),
            option_price=int(opt.get("optionPrice", 0)),
            stock=int(opt.get("stockQuantity", 0)),
        )
        for opt in options_raw
    ]
    return ProductInfo(
        product_id=str(item.get("productId", "")),
        product_name=item.get("productName", ""),
        sale_price=int(item.get("salePrice", 0)),
        discount_amount=int(item.get("discountAmount", 0)),
        options=options,
    )


# ──────────────────────────────────────────────
# 개발/테스트용 목(mock) 데이터
# ──────────────────────────────────────────────

def _mock_search(query: str) -> List[ProductInfo]:
    """API 미연결 시 사용하는 목 데이터"""
    logger.info("목 데이터로 검색 결과를 반환합니다: %r", query)
    return [_mock_product("MOCK001"), _mock_product("MOCK002")]


def _mock_product(product_id: str) -> ProductInfo:
    return ProductInfo(
        product_id=product_id,
        product_name=f"[테스트] 닭가슴살 모음 ({product_id})",
        sale_price=15000,
        discount_amount=1000,
        options=[
            OptionItem(option_id="OPT001", option_name="닭가슴살 1kg 냉동", option_price=0, stock=100),
            OptionItem(option_id="OPT002", option_name="닭안심 500g 냉동", option_price=0, stock=80),
            OptionItem(option_id="OPT003", option_name="닭다리살 200g 냉장", option_price=0, stock=50),
            OptionItem(option_id="OPT004", option_name="닭가슴살 500g 냉장", option_price=500, stock=60),
        ],
    )
