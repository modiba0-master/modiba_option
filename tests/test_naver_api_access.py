"""
네이버 커머스 API 접근 권한 확인 스크립트

실행: python tests/test_naver_api_access.py
"""

import asyncio
import base64
import time
import json
import sys
import os

import bcrypt
import httpx

# ──────────────────────────────────────────────
# 자격증명 (환경변수 우선, 없으면 직접 지정)
# ──────────────────────────────────────────────
CLIENT_ID = os.getenv("NAVER_COMMERCE_API_CLIENT_ID", "CFKugaEoCihTsC7JRAnE0")
CLIENT_SECRET = os.getenv(
    "NAVER_COMMERCE_API_CLIENT_SECRET",
    "$2a$04$KocbA52MQNLUA5eEh5HTl."
)

BASE_URL = "https://api.commerce.naver.com/external"
TOKEN_URL = f"{BASE_URL}/v1/oauth2/token"
PRODUCT_ID = "6774969928"


def make_signature(client_id: str, client_secret: str, timestamp: int) -> str:
    """
    네이버 커머스 API 전자서명 생성
    방식: bcrypt.hashpw(password="{client_id}_{timestamp}", salt=client_secret) -> Base64
    """
    password = f"{client_id}_{timestamp}"
    hashed = bcrypt.hashpw(password.encode("utf-8"), client_secret.encode("utf-8"))
    return base64.b64encode(hashed).decode("utf-8")


async def step1_get_token() -> str | None:
    """Step 1: OAuth2 액세스 토큰 발급"""
    print("\n" + "=" * 60)
    print("【Step 1】 OAuth2 토큰 발급 테스트")
    print(f"  CLIENT_ID    : {CLIENT_ID}")
    print(f"  CLIENT_SECRET: {CLIENT_SECRET[:8]}...({len(CLIENT_SECRET)}자)")

    timestamp = int(time.time() * 1000)
    signature = make_signature(CLIENT_ID, CLIENT_SECRET, timestamp)

    print(f"  timestamp    : {timestamp}")
    print(f"  signature    : {signature[:20]}...")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "timestamp": timestamp,
                "client_secret_sign": signature,
                "grant_type": "client_credentials",
                "type": "SELF",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    print(f"\n  HTTP Status  : {resp.status_code}")

    try:
        data = resp.json()
        print(f"  Response     : {json.dumps(data, ensure_ascii=False, indent=2)}")
    except Exception:
        print(f"  Response(raw): {resp.text[:400]}")
        data = {}

    if resp.status_code == 200 and "access_token" in data:
        token = data["access_token"]
        print(f"\n  ✅ 토큰 발급 성공! (앞 20자: {token[:20]}...)")
        return token
    else:
        print("\n  ❌ 토큰 발급 실패")
        _print_error_hint(data)
        return None


async def step2_get_product(token: str) -> None:
    """Step 2: 상품 상세 조회"""
    print("\n" + "=" * 60)
    print(f"【Step 2】 상품 조회 테스트 (상품ID: {PRODUCT_ID})")

    url = f"{BASE_URL}/v1/products/{PRODUCT_ID}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers)

    print(f"  HTTP Status  : {resp.status_code}")

    try:
        data = resp.json()
        print(f"  Response     : {json.dumps(data, ensure_ascii=False, indent=2)[:600]}")
    except Exception:
        print(f"  Response(raw): {resp.text[:400]}")
        data = {}

    if resp.status_code == 200:
        print(f"\n  ✅ 상품 조회 성공!")
    else:
        print(f"\n  ❌ 상품 조회 실패")
        _print_error_hint(data)


async def step3_search_product(token: str) -> None:
    """Step 3: 상품 검색 테스트"""
    print("\n" + "=" * 60)
    print(f"【Step 3】 상품 검색 테스트 (키워드: {PRODUCT_ID})")

    url = f"{BASE_URL}/v1/products/search"
    params = {"productIds": PRODUCT_ID}
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers, params=params)

    print(f"  HTTP Status  : {resp.status_code}")
    try:
        data = resp.json()
        print(f"  Response     : {json.dumps(data, ensure_ascii=False, indent=2)[:800]}")
    except Exception:
        print(f"  Response(raw): {resp.text[:400]}")


def _print_error_hint(data: dict) -> None:
    code = data.get("code", "")
    msg = data.get("message", "")
    invalid = data.get("invalidInputs", [])

    if code == "Unauthorized":
        print("  💡 원인: 클라이언트 ID 또는 시크릿이 잘못되었습니다.")
    elif code == "BadRequest":
        print(f"  💡 원인: 요청 형식 오류 — {msg}")
        for inv in invalid:
            print(f"     - {inv.get('name')}: {inv.get('message')}")
    elif code == "Forbidden":
        print("  💡 원인: API 접근 권한 없음. 네이버 커머스 개발자센터에서 권한 확인 필요.")
    elif code == "NotFound":
        print(f"  💡 원인: 상품 {PRODUCT_ID}가 해당 계정의 스토어에 존재하지 않습니다.")


async def main():
    print("=" * 60)
    print("  네이버 커머스 API 접근 권한 확인")
    print("=" * 60)

    token = await step1_get_token()
    if not token:
        print("\n🛑 토큰 발급 실패로 이후 테스트를 건너뜁니다.")
        sys.exit(1)

    await step2_get_product(token)
    await step3_search_product(token)

    print("\n" + "=" * 60)
    print("  테스트 완료")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
