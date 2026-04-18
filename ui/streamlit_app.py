"""
Streamlit UI - 옵션명 기반 가격 계산 엔진
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
    page_title="모디바 옵션 가격 계산기",
    page_icon="🧮",
    layout="wide",
)

DEFAULT_PRODUCT_ID = os.getenv("DEFAULT_PRODUCT_ID", "6774969928")

# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
[data-testid="stMetricLabel"] { font-size: 0.85rem; color: #555; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
div[data-testid="stDataFrame"] { border: 1px solid #e0e0e0; border-radius: 8px; }
.stAlert { border-radius: 8px; }
h3 { margin-top: 0.5rem !important; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────────
def _get_server_ip() -> str:
    import urllib.request
    for url in ["https://api.ipify.org", "https://icanhazip.com"]:
        try:
            return urllib.request.urlopen(url, timeout=5).read().decode().strip()
        except Exception:
            continue
    return "조회 실패"


def _test_naver_api() -> dict:
    import base64, time
    import bcrypt, httpx

    cid = os.getenv("NAVER_COMMERCE_API_CLIENT_ID", "")
    csecret = os.getenv("NAVER_COMMERCE_API_CLIENT_SECRET", "")
    if not cid or not csecret:
        return {"ok": False, "msg": "환경변수 미설정"}

    ts = int(time.time() * 1000)
    hashed = bcrypt.hashpw(f"{cid}_{ts}".encode(), csecret.encode())
    sig = base64.b64encode(hashed).decode()

    try:
        r = httpx.post(
            "https://api.commerce.naver.com/external/v1/oauth2/token",
            data={"client_id": cid, "timestamp": ts, "client_secret_sign": sig,
                  "grant_type": "client_credentials", "type": "SELF"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10,
        )
        d = r.json()
    except Exception as e:
        return {"ok": False, "msg": str(e)}

    if r.status_code != 200 or "access_token" not in d:
        return {"ok": False, "code": d.get("code", ""), "msg": d.get("message", "")[:100]}

    return {"ok": True, "token_prefix": d["access_token"][:20]}


with st.sidebar:
    # ── API 상태 표시
    cid_set = bool(os.getenv("NAVER_COMMERCE_API_CLIENT_ID", ""))
    if cid_set:
        st.success("✅ 네이버 API 연결됨")
    else:
        st.error("❌ API 자격증명 미설정")
    st.caption(f"기본 상품ID: **{DEFAULT_PRODUCT_ID}**")

    st.divider()

    # ── 개발자 도구 (접힌 상태)
    with st.expander("🛠️ 개발자 도구", expanded=False):
        if st.button("🌐 서버 IP 확인", use_container_width=True):
            with st.spinner("조회 중..."):
                ip = _get_server_ip()
            st.session_state["server_ip"] = ip

        if "server_ip" in st.session_state:
            st.code(st.session_state["server_ip"], language=None)
            st.caption("👆 네이버 API 화이트리스트 등록 IP")

        st.markdown("---")

        if st.button("🧪 API 연결 테스트", use_container_width=True):
            with st.spinner("테스트 중..."):
                res = _test_naver_api()
            st.session_state["api_test"] = res

        if "api_test" in st.session_state:
            res = st.session_state["api_test"]
            if res.get("ok"):
                st.success("API 정상")
                st.caption(f"토큰: {res.get('token_prefix','')}...")
            else:
                st.error(f"실패: {res.get('code','')} {res.get('msg','')}")

    st.divider()
    st.markdown(
        "<small>조회 + 계산 + 엑셀 출력 전용<br>가격 자동반영 기능 없음</small>",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────
# 헤더
# ──────────────────────────────────────────────
st.title("🧮 모디바 옵션 가격 계산기")
st.caption("네이버 커머스 상품의 옵션 가격을 가중치 기반으로 재계산하고 엑셀로 출력합니다.")
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
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ──────────────────────────────────────────────
# 세션 초기화
# ──────────────────────────────────────────────
for key, default in [
    ("search_results", []),
    ("selected_product", None),
    ("calc_results", None),
    ("auto_loaded", False),
    ("last_query", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ──────────────────────────────────────────────
# 기본 상품 자동 로드 (최초 1회)
# ──────────────────────────────────────────────
if not st.session_state.auto_loaded:
    with st.spinner(f"상품 {DEFAULT_PRODUCT_ID} 불러오는 중..."):
        product = run_async(naver_api.get_product_detail(DEFAULT_PRODUCT_ID))
    if product:
        # API에서 product_id가 비면 검색한 ID로 채움
        if not product.product_id:
            product = product.model_copy(update={"product_id": DEFAULT_PRODUCT_ID})
        st.session_state.selected_product = product
        st.session_state.search_results = [product]
    st.session_state.auto_loaded = True


# ──────────────────────────────────────────────
# ① 검색
# ──────────────────────────────────────────────
st.subheader("① 상품 검색")
col_search, col_btn = st.columns([5, 1])
with col_search:
    query = st.text_input(
        "상품ID 또는 상품명",
        placeholder="예: 6774969928",
        label_visibility="collapsed",
    )
with col_btn:
    search_clicked = st.button("🔍 검색", use_container_width=True)

if search_clicked and query.strip():
    with st.spinner("검색 중..."):
        results = run_async(naver_api.search_products(query.strip()))
    # 검색 결과에도 product_id 빈 값 보완
    for p in results:
        if not p.product_id and query.strip().isdigit():
            p.product_id = query.strip()
    st.session_state.search_results = results
    st.session_state.selected_product = None
    st.session_state.calc_results = None
    st.session_state.last_query = query.strip()
    if not results:
        st.warning("검색 결과가 없습니다.")


# ──────────────────────────────────────────────
# ② 상품 선택
# ──────────────────────────────────────────────
if st.session_state.search_results:
    st.subheader("② 상품 선택")
    product_options = {}
    for p in st.session_state.search_results:
        pid = p.product_id or st.session_state.last_query or DEFAULT_PRODUCT_ID
        label = f"[{pid}] {p.product_name}" if p.product_name else f"[{pid}]"
        product_options[label] = p

    labels = list(product_options.keys())
    default_idx = 0
    if st.session_state.selected_product:
        sp_id = st.session_state.selected_product.product_id
        for i, lbl in enumerate(labels):
            if sp_id and sp_id in lbl:
                default_idx = i
                break

    selected_label = st.selectbox("상품 목록", labels, index=default_idx, label_visibility="collapsed")
    if selected_label:
        st.session_state.selected_product = product_options[selected_label]


# ──────────────────────────────────────────────
# ③ 상품 상세 + ④ 가중치
# ──────────────────────────────────────────────
if st.session_state.selected_product:
    product = st.session_state.selected_product
    display_id = product.product_id or DEFAULT_PRODUCT_ID
    st.divider()

    col_detail, col_weight = st.columns([3, 2])

    with col_detail:
        # 상품 기본 정보
        st.subheader("③ 상품 상세")
        st.markdown(f"**{product.product_name}**")
        st.caption(f"상품 번호: {display_id}")

        m1, m2, m3 = st.columns(3)
        m1.metric("판매가", f"{product.sale_price:,}원")
        m2.metric("기본할인", f"▼ {product.discount_amount:,}원")
        m3.metric("할인가", f"{product.discounted_price:,}원")

        st.markdown("")

        # 기준가 설정
        st.subheader("⑤ 계산 기준가")
        default_base = product.discounted_price if product.discounted_price > 0 else product.sale_price
        base_price = st.number_input(
            "기준가 (원)",
            min_value=1,
            value=default_base,
            step=100,
            help="P_option = 기준가 × W_중량 × W_부위 × W_보관",
            label_visibility="collapsed",
        )
        st.caption(f"기준가: **{base_price:,}원** (할인가 기준, 직접 수정 가능)")

        st.markdown("")

        # 옵션 목록
        st.subheader(f"📋 현재 옵션 목록 ({len(product.options)}개)")
        if product.options:
            opt_df = pd.DataFrame([
                {
                    "옵션명": o.option_name,
                    "옵션가": f"{o.option_price:,}원" if o.option_price else "—",
                    "재고": f"{o.stock:,}개",
                    "옵션ID": o.option_id,
                }
                for o in product.options
            ])
            st.dataframe(opt_df, use_container_width=True, hide_index=True, height=280)
        else:
            st.info("옵션 정보가 없습니다.")

    with col_weight:
        st.subheader("④ 가중치 설정")
        st.caption("속성별 가중치를 조정하면 계산가가 바뀝니다.")

        with st.expander("⚖️ 중량 가중치", expanded=True):
            weight_map = {}
            for key, dv in DEFAULT_WEIGHT_MAP.items():
                weight_map[key] = st.number_input(
                    f"{key}", min_value=0.01, max_value=10.0,
                    value=dv, step=0.01, format="%.2f", key=f"w_{key}",
                )

        with st.expander("🍗 부위 가중치", expanded=True):
            part_map = {}
            for key, dv in DEFAULT_PART_MAP.items():
                part_map[key] = st.number_input(
                    f"{key}", min_value=0.01, max_value=10.0,
                    value=dv, step=0.01, format="%.2f", key=f"p_{key}",
                )

        with st.expander("❄️ 보관방식 가중치", expanded=True):
            storage_map = {}
            for key, dv in DEFAULT_STORAGE_MAP.items():
                storage_map[key] = st.number_input(
                    f"{key}", min_value=0.01, max_value=10.0,
                    value=dv, step=0.01, format="%.2f", key=f"s_{key}",
                )

        st.markdown("")
        st.info(
            "**계산 공식**\n\n"
            "변경가 = 기준가 × 중량 × 부위 × 보관",
            icon="📐",
        )


    # ──────────────────────────────────────────────
    # ⑥ 계산 실행
    # ──────────────────────────────────────────────
    st.divider()
    st.subheader("⑥ 계산 실행 및 미리보기")

    if st.button("🧮 가격 계산 실행", use_container_width=True, type="primary"):
        if not product.options:
            st.warning("옵션 정보가 없어 계산할 수 없습니다.")
        else:
            config = WeightConfig()
            config.update(weight_map=weight_map, part_map=part_map, storage_map=storage_map)
            calculated = calculate_all_options(base_price, product.options, config)
            st.session_state.calc_results = CalculationResult(
                product_id=display_id,
                product_name=product.product_name,
                sale_price=product.sale_price,
                discount_amount=product.discount_amount,
                discounted_price=product.discounted_price,
                base_price_used=base_price,
                options=calculated,
            )

    if st.session_state.calc_results:
        result = st.session_state.calc_results

        st.success(
            f"계산 완료 | 상품: **{result.product_name[:30]}{'...' if len(result.product_name) > 30 else ''}** "
            f"| 기준가: **{result.base_price_used:,}원** | 총 **{len(result.options)}개** 옵션"
        )

        # 비교 테이블 구성
        rows = []
        for o in result.options:
            diff = o.calculated_price - o.original_price
            rows.append({
                "옵션명": o.option_name,
                "중량": o.weight or "—",
                "부위": o.part or "—",
                "보관": o.storage or "—",
                "기존 옵션가": o.original_price,
                "변경 옵션가": o.calculated_price,
                "차이(원)": diff,
                "재고": o.stock,
            })

        df = pd.DataFrame(rows)

        # 숫자 포맷 및 하이라이트
        def fmt_price(v):
            return f"{v:,}" if isinstance(v, (int, float)) else v

        def color_diff(v):
            if isinstance(v, (int, float)):
                if v > 0:
                    return "color: #1a7f37; font-weight:bold"
                if v < 0:
                    return "color: #d73a49; font-weight:bold"
            return ""

        styled = (
            df.style
            .format({
                "기존 옵션가": "{:,}원",
                "변경 옵션가": "{:,}원",
                "차이(원)": lambda v: f"+{v:,}" if v >= 0 else f"{v:,}",
                "재고": "{:,}개",
            })
            .applymap(color_diff, subset=["차이(원)"])
        )

        st.dataframe(styled, use_container_width=True, hide_index=True, height=320)

        # 간단 통계
        avg_before = df["기존 옵션가"].mean()
        avg_after = df["변경 옵션가"].mean()
        s1, s2, s3 = st.columns(3)
        s1.metric("평균 기존 옵션가", f"{avg_before:,.0f}원")
        s2.metric("평균 변경 옵션가", f"{avg_after:,.0f}원")
        s3.metric("평균 변동", f"{avg_after - avg_before:+,.0f}원")

        # ⑦ 엑셀 다운로드
        st.divider()
        st.subheader("⑦ 엑셀 다운로드")
        c_info, c_btn = st.columns([3, 1])
        with c_info:
            st.caption(
                f"파일명: `option_price_{result.product_id}.xlsx` "
                f"| {len(result.options)}개 옵션 | 기준가 {result.base_price_used:,}원"
            )
        with c_btn:
            excel_bytes = build_excel_bytes(result)
            st.download_button(
                label="📥 엑셀 다운로드",
                data=excel_bytes,
                file_name=f"option_price_{result.product_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
