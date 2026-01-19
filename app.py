import datetime
from io import BytesIO
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from dotenv import load_dotenv

# --- 환경 설정 ---
load_dotenv()
db_name = os.getenv('DB_NAME', '주가 추이 확인')
st.header(db_name)

# --- 1. 세션 상태 초기화 (사이드바 버튼 연동용) ---
if 'company_name' not in st.session_state:
    st.session_state.company_name = ""
if 'auto_submit' not in st.session_state:
    st.session_state.auto_submit = False

# --- 2. 데이터 관련 함수 ---
@st.cache_data(ttl=3600)
def get_fixed_top_10():
    """대표 주식 10개의 현재가와 등락률 계산"""
    stocks = {
        '삼성전자': '005930', 'SK하이닉스': '000660', 'LG에너지솔루션': '373220',
        '삼성바이오로직스': '207940', '현대차': '005380', '기아': '000270',
        '셀트리온': '068270', 'KB금융': '105560', 'NAVER': '035420', '신한지주': '055550'
    }
    results = []
    for name, code in stocks.items():
        try:
            # 등락률 계산을 위해 최근 7일치 데이터 호출
            df = fdr.DataReader(code, (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d'))
            if not df.empty:
                current_price = df['Close'].iloc[-1]
                prev_price = df['Close'].iloc[-2]
                chg_rate = ((current_price - prev_price) / prev_price) * 100
                results.append({'Name': name, 'Close': current_price, 'ChgRate': chg_rate})
        except:
            continue
    return pd.DataFrame(results)

@st.cache_data
def get_krx_company_list() -> pd.DataFrame:
    """상장사 명단 로드"""
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        df_listing = pd.read_html(url, header=0, flavor='bs4', encoding='EUC-KR')[0]
        df_listing = df_listing[['회사명', '종목코드']].copy()
        df_listing['종목코드'] = df_listing['종목코드'].apply(lambda x: f'{x:06}')
        return df_listing
    except:
        return pd.DataFrame(columns=['회사명', '종목코드'])

def get_stock_code_by_company(company_name: str) -> str:
    """회사명으로 종목코드 찾기"""
    if company_name.isdigit() and len(company_name) == 6:
        return company_name
    company_df = get_krx_company_list()
    codes = company_df[company_df['회사명'] == company_name]['종목코드'].values
    if len(codes) > 0:
        return codes[0]
    else:
        raise ValueError(f"'{company_name}'을 찾을 수 없습니다.")

# --- 3. 사이드바 UI ---
# 기존 입력창 구조 유지 + 세션값 반영
company_name_input = st.sidebar.text_input(
    '조회할 회사를 입력하세요', 
    value=st.session_state.company_name,
    key="main_search_input"
)

today = datetime.datetime.now()
selected_dates = st.sidebar.date_input(
    "조회 기간",
    (datetime.date(today.year, 1, 1), today),
    format="YYYY.MM.DD",
)

confirm_btn = st.sidebar.button('조회하기', use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### 주요 종목 10선")
top_df = get_fixed_top_10()

if not top_df.empty:
    h_cols = st.sidebar.columns([2, 1, 1])
    h_cols[0].caption("주식명")
    h_cols[1].caption("종가")
    h_cols[2].caption("등락")

    for i, row in top_df.iterrows():
        cols = st.sidebar.columns([2, 1, 1])
        if cols[0].button(row['Name'], key=f"top_btn_{i}"):
            st.session_state.company_name = row['Name']
            st.session_state.auto_submit = True
            st.rerun()
            
        color = "red" if row['ChgRate'] > 0 else "blue" if row['ChgRate'] < 0 else "white"
        cols[1].write(f"{int(row['Close']):,}")
        cols[2].markdown(f":{color}[{row['ChgRate']:.1f}%]")

# --- 4. 메인 분석 로직 ---
if confirm_btn or st.session_state.auto_submit:
    # 검색할 대상 확정
    search_target = st.session_state.company_name if st.session_state.auto_submit else company_name_input
    st.session_state.auto_submit = False  # 플래그 초기화
    
    if not search_target:
        st.warning("회사 이름을 입력해 주세요.")
    else:
        try:
            with st.spinner(f'{search_target} 데이터를 가져오는 중...'):
                stock_code = get_stock_code_by_company(search_target)
                start_date = selected_dates[0].strftime("%Y%m%d")
                end_date = selected_dates[1].strftime("%Y%m%d")
                price_df = fdr.DataReader(stock_code, start_date, end_date)
                
            if price_df.empty:
                st.info("해당 기간의 주가 데이터가 없습니다.")
            else:
                st.subheader(f"{search_target} 분석 결과")

                # (1) [기존 기능] 데이터 프레임 상위 5개 출력
                st.write("최근 데이터 내역 (상위 5행)")
                st.dataframe(price_df.tail(5)) # 최근 날짜가 아래이므로 tail 권장

                # 지표 계산
                price_df['MA5'] = price_df['Close'].rolling(5).mean()
                price_df['MA20'] = price_df['Close'].rolling(20).mean()
                price_df['MA60'] = price_df['Close'].rolling(60).mean()
                price_df['MA120'] = price_df['Close'].rolling(120).mean()

                # (2) [신규 기능] 캔들스틱 + 이동평균선 + 거래량 차트
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                    vertical_spacing=0.05, row_heights=[0.7, 0.3])

                fig.add_trace(go.Candlestick(
                    x=price_df.index, open=price_df['Open'], high=price_df['High'],
                    low=price_df['Low'], close=price_df['Close'], name="캔들차트",
                    increasing_line_color='red', decreasing_line_color='blue'
                ), row=1, col=1)

                ma_colors = [('MA5', 'green'), ('MA20', 'red'), ('MA60', 'orange'), ('MA120', 'purple')]
                for ma, color in ma_colors:
                    fig.add_trace(go.Scatter(x=price_df.index, y=price_df[ma], name=ma, 
                                             line=dict(color=color, width=1)), row=1, col=1)

                vol_colors = ['red' if price_df.Open[i] < price_df.Close[i] else 'blue' for i in range(len(price_df))]
                fig.add_trace(go.Bar(x=price_df.index, y=price_df['Volume'], name="거래량", 
                                     marker_color=vol_colors, showlegend=False), row=2, col=1)

                fig.update_layout(height=600, template="plotly_white", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

                # (3) [기존 기능] Box Plot 변동성 분석
                st.markdown(f"#### {search_target} 기간별 종가 변동성 (Box Plot)")
                fig_box = go.Figure()
                fig_box.add_trace(go.Box(y=price_df['Close'], name='종가 변동성', marker_color='royalblue'))
                fig_box.update_layout(height=400, template="plotly_white")
                st.plotly_chart(fig_box, use_container_width=True)

                # (4) [기존 기능] 엑셀 다운로드
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    price_df.to_excel(writer, index=True)
                st.download_button(
                    label="📥 엑셀 파일 다운로드",
                    data=output.getvalue(),
                    file_name=f"{search_target}_주가데이터.xlsx",
                    mime="application/vnd.ms-excel"
                )

        except Exception as e:
            st.error(f"오류: {e}")