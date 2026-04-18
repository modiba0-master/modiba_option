"""
Streamlit UI - 옵션명 기반 가격 계산 엔진

실행: streamlit run ui/streamlit_app.py
"""

import asyncio
import sys
import os

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import naver_api
from app.services.weight_manager import (
    WeightConfig,
    DEFAULT_WEIGHT_MAP,
    DEFAULT_PART_MAP,
    DEFAULT_STORAGE_MAP,
)
from app.services.price_engine import calculate_all_options
from app.services.excel_exporter import build_excel_bytes
from app.models.product_model import CalculationResult


# ──────────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="옵션 가격 계산 엔진",
    page_icon="🧮",
    layout="wide",
)

st.title("🧮 옵션명 기반 가격 계산 엔진")
st.caption("네이버 커머스 상품 데이터를 조회하고, 옵션 가격을 재계산하여 엑셀로 출력합니다.")
st.warning(
    "⚠️ 본 도구는 **조회 + 계산 + 엑셀 출력** 전용입니다. "
    "네이버 서버에 가격을 반영하는 기능은 포함되어 있지 않습니다.",
    icon="🔒",
)

st.divider()


# ──────────────────────────────────────────────
# 비동기 헬퍼
# ──────────────────────────────────────────────
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ──────────────────────────────────────────────
# 세션 초기화
# ──────────────────────────────────────────────
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "selected_product" not in st.session_state:
    st.session_state.selected_product = None
if "calc_results" not in st.session_state:
    st.session_state.calc_results = None


# ──────────────────────────────────────────────
# 1. 검색 영역
# ──────────────────────────────────────────────
st.subheader("1️⃣ 상품 검색")
col_search, col_btn = st.columns([4, 1])
with col_search:
    query = st.text_input("상품ID 또는 상품명을 입력하세요", placeholder="예: 닭가슴살, 12345678")
with col_btn:
    st.write("")
    search_clicked = st.button("🔍 검색", use_container_width=True)

if search_clicked and query.strip():
    with st.spinner("상품을 검색 중입니다..."):
        results = run_async(naver_api.search_products(query.strip()))
    st.session_state.search_results = results
    st.session_state.selected_product = None
    st.session_state.calc_results = None

    if not results:
        st.info("검색 결과가 없습니다.")


# ──────────────────────────────────────────────
# 2. 상품 선택
# ──────────────────────────────────────────────
if st.session_state.search_results:
    st.subheader("2️⃣ 상품 선택")
    product_options = {
        f"[{p.product_id}] {p.product_name}": p
        for p in st.session_state.search_results
    }
    selected_label = st.selectbox("검색된 상품 목록", list(product_options.keys()))
    if selected_label:
        st.session_state.selected_product = product_options[selected_label]


# ──────────────────────────────────────────────
# 3. 상품 상세 + 가중치 설정
# ──────────────────────────────────────────────
if st.session_state.selected_product:
    product = st.session_state.selected_product
    st.divider()

    col_detail, col_weight = st.columns([3, 2])

    with col_detail:
        st.subheader("3️⃣ 상품 상세")
        st.markdown(f"**상품명:** {product.product_name}")
        st.markdown(f"**상품ID:** `{product.product_id}`")

        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("판매가", f"{product.sale_price:,}원")
        col_p2.metric("기본할인", f"{product.discount_amount:,}원")
        col_p3.metric("할인가", f"{product.discounted_price:,}원")

        st.subheader("5️⃣ 기준가 설정")
        base_price = st.number_input(
            "계산에 사용할 기준가 (원)",
            min_value=1,
            value=product.discounted_price if product.discounted_price > 0 else product.sale_price,
            step=100,
        )

        st.subheader("옵션 목록")
        if product.options:
            opt_df = pd.DataFrame([
                {
                    "옵션ID": o.option_id,
                    "옵션명": o.option_name,
                    "옵션가(기존)": o.option_price,
                    "재고": o.stock,
                }
                for o in product.options
            ])
            st.dataframe(opt_df, use_container_width=True, hide_index=True)
        else:
            st.info("옵션 정보가 없습니다.")

    with col_weight:
        st.subheader("4️⃣ 가중치 설정")

        st.markdown("**중량 가중치**")
        weight_map = {}
        for key, default_val in DEFAULT_WEIGHT_MAP.items():
            weight_map[key] = st.number_input(
                f"  {key}", min_value=0.01, max_value=10.0,
                value=default_val, step=0.01, key=f"w_{key}"
            )

        st.markdown("**부위 가중치**")
        part_map = {}
        for key, default_val in DEFAULT_PART_MAP.items():
            part_map[key] = st.number_input(
                f"  {key}", min_value=0.01, max_value=10.0,
                value=default_val, step=0.01, key=f"p_{key}"
            )

        st.markdown("**보관방식 가중치**")
        storage_map = {}
        for key, default_val in DEFAULT_STORAGE_MAP.items():
            storage_map[key] = st.number_input(
                f"  {key}", min_value=0.01, max_value=10.0,
                value=default_val, step=0.01, key=f"s_{key}"
            )

    # ──────────────────────────────────────────────
    # 6. 계산 실행 및 미리보기
    # ──────────────────────────────────────────────
    st.divider()
    st.subheader("6️⃣ 계산 실행 및 미리보기")

    if st.button("🧮 가격 계산 실행", use_container_width=True, type="primary"):
        config = WeightConfig()
        config.update(weight_map=weight_map, part_map=part_map, storage_map=storage_map)

        calculated = calculate_all_options(base_price, product.options, config)
        st.session_state.calc_results = CalculationResult(
            product_id=product.product_id,
            product_name=product.product_name,
            sale_price=product.sale_price,
            discount_amount=product.discount_amount,
            discounted_price=product.discounted_price,
            base_price_used=base_price,
            options=calculated,
        )

    if st.session_state.calc_results:
        result = st.session_state.calc_results
        st.success(f"계산 완료 — 기준가: **{result.base_price_used:,}원**")

        preview_df = pd.DataFrame([
            {
                "옵션명": o.option_name,
                "옵션가 (기존)": o.original_price,
                "변경옵션가 (계산값)": o.calculated_price,
                "차이": o.calculated_price - o.original_price,
                "재고": o.stock,
                "중량": o.weight or "-",
                "부위": o.part or "-",
                "보관": o.storage or "-",
            }
            for o in result.options
        ])
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

        # ──────────────────────────────────────────────
        # 7. 엑셀 다운로드
        # ──────────────────────────────────────────────
        st.subheader("7️⃣ 엑셀 다운로드")
        excel_bytes = build_excel_bytes(result)
        st.download_button(
            label="📥 엑셀 파일 다운로드",
            data=excel_bytes,
            file_name=f"option_price_{result.product_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
