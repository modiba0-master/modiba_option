"""
Streamlit UI - 모디바 옵션 가격 계산기
옵션별 가중치 방식: 변경가 = 대표 기준가 × 옵션가중치
"""

import asyncio
import sys
import os

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import naver_api
from app.services.excel_exporter import build_excel_bytes
from app.models.product_model import CalculationResult, CalculatedOption

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
[data-testid="stMetricLabel"] { font-size: 0.8rem; color: #666; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
div[data-testid="stDataFrame"] { border: 1px solid #e0e0e0; border-radius: 8px; }
.stAlert { border-radius: 8px; }
.option-row { padding: 2px 0; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# 유틸리티
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


def suggest_weight(option_price: int, base_price: int) -> float:
    """기존 옵션가(상대값)에서 가중치를 역산합니다."""
    if base_price <= 0:
        return 1.0
    actual = base_price + option_price
    if actual <= 0:
        return 1.0
    return round(actual / base_price, 2)


def get_weight_key(option_id: str) -> str:
    return f"opt_w_{option_id}"


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
    cid_set = bool(os.getenv("NAVER_COMMERCE_API_CLIENT_ID", ""))
    if cid_set:
        st.success("✅ 네이버 API 연결됨")
    else:
        st.error("❌ API 자격증명 미설정")
    st.caption(f"기본 상품ID: **{DEFAULT_PRODUCT_ID}**")
    st.divider()
    with st.expander("🛠️ 개발자 도구", expanded=False):
        if st.button("🌐 서버 IP 확인", use_container_width=True):
            with st.spinner("조회 중..."):
                st.session_state["server_ip"] = _get_server_ip()
        if "server_ip" in st.session_state:
            st.code(st.session_state["server_ip"], language=None)
            st.caption("👆 네이버 API 화이트리스트 등록 IP")
        st.markdown("---")
        if st.button("🧪 API 연결 테스트", use_container_width=True):
            with st.spinner("테스트 중..."):
                st.session_state["api_test"] = _test_naver_api()
        if "api_test" in st.session_state:
            res = st.session_state["api_test"]
            if res.get("ok"):
                st.success("API 정상")
            else:
                st.error(f"{res.get('code','')} {res.get('msg','')}")
    st.divider()
    st.markdown(
        "<small>조회 + 계산 + 엑셀 출력 전용<br>가격 자동반영 기능 없음</small>",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────
# 헤더
# ──────────────────────────────────────────────
st.title("🧮 모디바 옵션 가격 계산기")
st.caption("대표 기준가를 설정하면 옵션별 가중치에 따라 변경가가 자동으로 계산됩니다.")
st.divider()


# ──────────────────────────────────────────────
# 세션 초기화
# ──────────────────────────────────────────────
for key, default in [
    ("search_results", []),
    ("selected_product", None),
    ("calc_results", None),
    ("auto_loaded", False),
    ("last_query", ""),
    ("weights_initialized_for", ""),  # product_id 기준 초기화 여부 추적
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
        if not product.product_id:
            product = product.model_copy(update={"product_id": DEFAULT_PRODUCT_ID})
        st.session_state.selected_product = product
        st.session_state.search_results = [product]
    st.session_state.auto_loaded = True


# ──────────────────────────────────────────────
# ① 상품 검색
# ──────────────────────────────────────────────
st.subheader("① 상품 검색")
col_s, col_b = st.columns([5, 1])
with col_s:
    query = st.text_input("상품ID", placeholder="예: 6774969928",
                          label_visibility="collapsed")
with col_b:
    if st.button("🔍 검색", use_container_width=True):
        if query.strip():
            with st.spinner("검색 중..."):
                results = run_async(naver_api.search_products(query.strip()))
            for p in results:
                if not p.product_id and query.strip().isdigit():
                    p.product_id = query.strip()
            st.session_state.search_results = results
            st.session_state.selected_product = None
            st.session_state.last_query = query.strip()
            st.session_state.weights_initialized_for = ""
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

    selected_label = st.selectbox("상품 목록", labels, index=default_idx,
                                  label_visibility="collapsed")
    if selected_label:
        new_product = product_options[selected_label]
        if (st.session_state.selected_product is None or
                new_product.product_id != st.session_state.selected_product.product_id):
            st.session_state.weights_initialized_for = ""
        st.session_state.selected_product = new_product


# ──────────────────────────────────────────────
# 상품 상세 + 기준가 + 옵션별 가중치
# ──────────────────────────────────────────────
if st.session_state.selected_product:
    product = st.session_state.selected_product
    display_id = product.product_id or DEFAULT_PRODUCT_ID
    st.divider()

    # ③ 상품 상세 + ④ 기준가
    col_info, col_base = st.columns([2, 1])

    with col_info:
        st.subheader("③ 상품 상세")
        st.markdown(f"### {product.product_name}")
        st.caption(f"상품번호: {display_id} | 옵션 {len(product.options)}개")
        m1, m2, m3 = st.columns(3)
        m1.metric("판매가", f"{product.sale_price:,}원")
        m2.metric("기본할인", f"▼ {product.discount_amount:,}원")
        m3.metric("할인가", f"{product.discounted_price:,}원")

    with col_base:
        st.subheader("④ 대표 기준가")
        default_base = (product.discounted_price if product.discounted_price > 0
                        else product.sale_price)
        base_price = st.number_input(
            "기준가 (원)",
            min_value=1,
            value=default_base,
            step=100,
            label_visibility="collapsed",
            help="이 기준가 × 각 옵션 가중치 = 변경 계산가",
        )
        st.markdown(f"## **{base_price:,}원**")
        st.caption("변경가 = **기준가 × 옵션가중치**")

    st.divider()

    # ──────────────────────────────────────────────
    # ⑤ 옵션별 가중치 설정 (인라인 실시간 계산)
    # ──────────────────────────────────────────────
    st.subheader(f"⑤ 옵션별 가중치 설정 ({len(product.options)}개)")

    # 가중치 초기화: 새 상품이면 기존 옵션가에서 역산하여 자동 설정
    if st.session_state.weights_initialized_for != display_id:
        for opt in product.options:
            key = get_weight_key(opt.option_id)
            if key not in st.session_state:
                suggested = suggest_weight(opt.option_price, base_price)
                st.session_state[key] = suggested
        st.session_state.weights_initialized_for = display_id

    # 초기화 버튼
    col_hdr, col_reset = st.columns([4, 1])
    with col_hdr:
        st.caption("💡 가중치 초기값은 현재 옵션가에서 자동 역산됩니다. 직접 수정 가능합니다.")
    with col_reset:
        if st.button("🔄 가중치 초기화", use_container_width=True):
            for opt in product.options:
                key = get_weight_key(opt.option_id)
                st.session_state[key] = suggest_weight(opt.option_price, base_price)
            st.rerun()

    # 테이블 헤더
    h0, h1, h2, h3, h4 = st.columns([4, 1, 1, 1, 1])
    h0.markdown("**옵션명**")
    h1.markdown("**재고**")
    h2.markdown("**기존 옵션가**")
    h3.markdown("**가중치**")
    h4.markdown("**변경 계산가**")
    st.markdown("---")

    # 옵션 행 렌더링
    for opt in product.options:
        key = get_weight_key(opt.option_id)
        if key not in st.session_state:
            st.session_state[key] = suggest_weight(opt.option_price, base_price)

        c0, c1, c2, c3, c4 = st.columns([4, 1, 1, 1, 1])

        with c0:
            st.write(opt.option_name)
        with c1:
            st.write(f"{opt.stock:,}개")
        with c2:
            if opt.option_price == 0:
                st.write("—")
            elif opt.option_price > 0:
                st.write(f"+{opt.option_price:,}원")
            else:
                st.write(f"{opt.option_price:,}원")
        with c3:
            w = st.number_input(
                "가중치",
                min_value=0.01,
                max_value=20.0,
                value=float(st.session_state[key]),
                step=0.01,
                format="%.2f",
                key=key,
                label_visibility="collapsed",
            )
        with c4:
            calc = round(base_price * w)
            existing_actual = base_price + opt.option_price
            diff = calc - existing_actual
            diff_color = "#1a7f37" if diff >= 0 else "#d73a49"
            diff_str = f"+{diff:,}" if diff >= 0 else f"{diff:,}"
            st.markdown(
                f"**{calc:,}원**<br>"
                f"<span style='color:{diff_color};font-size:0.8rem'>{diff_str}</span>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ──────────────────────────────────────────────
    # ⑥ 전체 계산 결과 요약 테이블
    # ──────────────────────────────────────────────
    st.subheader("⑥ 계산 결과 요약")

    rows = []
    calculated_options = []
    for opt in product.options:
        key = get_weight_key(opt.option_id)
        w = float(st.session_state.get(key, 1.0))
        calc_price = round(base_price * w)
        existing_actual = base_price + opt.option_price
        diff = calc_price - existing_actual

        rows.append({
            "옵션명": opt.option_name,
            "현재 실판매가": existing_actual,
            "가중치": w,
            "변경 계산가": calc_price,
            "차이(원)": diff,
            "재고(개)": opt.stock,
        })

        calculated_options.append(CalculatedOption(
            option_id=opt.option_id,
            option_name=opt.option_name,
            original_price=existing_actual,
            calculated_price=calc_price,
            stock=opt.stock,
            weight=str(w),
        ))

    df = pd.DataFrame(rows)
    avg_before = df["현재 실판매가"].mean()
    avg_after = df["변경 계산가"].mean()

    # 통계 배너
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("기준가", f"{base_price:,}원")
    s2.metric("평균 현재가", f"{avg_before:,.0f}원")
    s3.metric("평균 변경가", f"{avg_after:,.0f}원")
    s4.metric("평균 변동", f"{avg_after - avg_before:+,.0f}원")

    # 결과 테이블
    def color_diff(v):
        if isinstance(v, (int, float)):
            if v > 0: return "color: #1a7f37; font-weight:bold"
            if v < 0: return "color: #d73a49; font-weight:bold"
        return ""

    styled = (
        df.style
        .format({
            "현재 실판매가": "{:,}원",
            "가중치": "{:.2f}",
            "변경 계산가": "{:,}원",
            "차이(원)": lambda v: f"+{v:,}" if v >= 0 else f"{v:,}",
            "재고(개)": "{:,}",
        })
        .applymap(color_diff, subset=["차이(원)"])
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=320)

    # ──────────────────────────────────────────────
    # ⑦ 엑셀 다운로드
    # ──────────────────────────────────────────────
    st.divider()
    st.subheader("⑦ 엑셀 다운로드")

    result = CalculationResult(
        product_id=display_id,
        product_name=product.product_name,
        sale_price=product.sale_price,
        discount_amount=product.discount_amount,
        discounted_price=product.discounted_price,
        base_price_used=base_price,
        options=calculated_options,
    )

    c_info, c_btn = st.columns([3, 1])
    with c_info:
        st.caption(
            f"파일명: `option_price_{display_id}.xlsx` "
            f"| {len(calculated_options)}개 옵션 | 기준가 {base_price:,}원"
        )
    with c_btn:
        excel_bytes = build_excel_bytes(result)
        st.download_button(
            label="📥 엑셀 다운로드",
            data=excel_bytes,
            file_name=f"option_price_{display_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
