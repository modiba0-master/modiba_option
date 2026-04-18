"""
FastAPI 애플리케이션 진입점

실행: uvicorn main:app --reload
문서: http://localhost:8000/docs
"""

import logging
import os

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import product, calculate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="옵션명 기반 가격 계산 엔진",
    description=(
        "네이버 커머스 API 상품 데이터를 조회하고, "
        "옵션명 파싱 및 가중치 기반 가격 재계산 결과를 엑셀로 출력합니다.\n\n"
        "⚠️ 이 API는 **조회 + 계산 + 엑셀 출력** 전용입니다. "
        "가격 수정·자동반영 기능은 포함되어 있지 않습니다."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(product.router)
app.include_router(calculate.router)


@app.get("/", tags=["상태 확인"])
async def root():
    return {"status": "ok", "message": "옵션 가격 계산 엔진이 정상 동작 중입니다."}


@app.get("/health", tags=["상태 확인"])
async def health():
    return {"status": "healthy"}


@app.get("/server-ip", tags=["상태 확인"], summary="서버 아웃바운드 IP 확인")
async def server_ip():
    """Railway 서버가 외부로 나가는 공인 IP를 반환합니다 (네이버 API IP 화이트리스트 등록용)."""
    sources = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]
    async with httpx.AsyncClient(timeout=8.0) as client:
        for url in sources:
            try:
                resp = await client.get(url)
                ip = resp.text.strip()
                return {"outbound_ip": ip, "source": url}
            except Exception:
                continue
    return {"outbound_ip": "조회 실패", "source": None}
