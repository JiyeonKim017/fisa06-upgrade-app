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
db_name = os.getenv('DB_NAME', '주가 데이터 분석 앱')
st.header(db_name)

# --- 1. 세션 상태 초기화 (클릭 이벤트 및 값 유지를 위함) ---
if 'company_name' not in st.session_state:
    st.session_state.company_name = ""
if 'auto_submit' not in st.session_state:
    st.session_state.auto_submit = False

# --- 2. 데이터 관련 함수 ---
@st.cache_data(ttl=3600)
def get_top_10_stocks():
    """시가총액 상위 10개 종목을 가져옵니다."""
    try:
        df = fdr.StockListing('KRX')
        top_10 = df.sort_values(by='Marcap', ascending=False).head(10)
        return top_10[['Name', 'Close', 'ChgRate']]
    except:
        return pd.DataFrame()

@st.cache_data
def get_krx_company_list() -> pd.DataFrame:
    """전체 상장사 명단을 가져옵니다."""
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        df_listing = pd.read_html(url, header=0, flavor='bs4', encoding='EUC-KR')[0]
        df_listing = df_listing[['회사명', '종목코드']].copy()
        df_listing['종목코드'] = df_listing['종목코드'].apply(lambda x: f'{x:06}')
        return df_listing
    except:
        return pd.DataFrame(columns=['회사명', '종목코드'])

def get_stock_code_by_company(company_name: str) -> str:
    """회사명으로 종목코드를 조회합니다."""
    if company_name.isdigit() and len(company_name) == 6:
        return company_name
    company_df = get_krx_company_list()
    codes = company_df[company_df['회사명'] == company_name]['종목코드'].values
    if len(codes) > 0:
        return codes[0]
    else:
        raise ValueError(f"'{company_name}'을 찾을 수 없습니다.")

# --- 3. 사이드바 구성 ---
st.sidebar.markdown("### 시가총액 TOP 10")
top_df = get_top_10_stocks()

if not top_df.empty:
    h_cols = st.sidebar.columns([2, 1, 1])
    h_cols[0].caption("주식명")
    h_cols[1].caption("종가")
    h_cols[2].caption("등락률")

    for i, row in top_df.iterrows():
        cols = st.sidebar.columns([2, 1, 1])
        # 종목명 버튼 클릭 시 세션 상태 업데이트 및 재실행
        if cols[0].button(row['Name'], key=f"top_btn_{i}"):
            st.session_state.company_name = row['Name']
            st.session_state.auto_submit = True
            st.rerun()
            
        color = "red" if row['ChgRate'] > 0 else "blue" if row['ChgRate'] < 0 else "white"
        cols[1].write(f"{int(row['Close']):,}")
        cols[2].markdown(f":{color}[{row['ChgRate']:.2f}%]")
else:
    st.sidebar.error("TOP 10 데이터를 불러올 수 없습니다.")

st.sidebar.markdown("---")

# 검색창 (세션 상태와 연결)
company_name_input = st.sidebar.text_input(
    '조회할 회사를 입력하세요', 
    value=st.session_state.company_name,
    key="main_search_input"
)

# 날짜 및 버튼
today = datetime.datetime.now()
selected_dates = st.sidebar.date_input(
    "조회 기간",
    (datetime.date(today.year, 1, 1), today),
    format="YYYY.MM.DD",
)
confirm_btn = st.sidebar.button('조회하기')

# --- 4. 메인 로직 ---
if confirm_btn or st.session_state.auto_submit:
    # 자동 제출 플래그 초기화
    st.session_state.auto_submit = False
    
    if not company_name_input:
        st.warning("조회할 회사 이름을 입력하세요.")
    else:
        try:
            with st.spinner('데이터를 수집하는 중...'):
                stock_code = get_stock_code_by_company(company_name_input)
                start_date = selected_dates[0].strftime("%Y%m%d")
                end_date = selected_dates[1].strftime("%Y%m%d")
                price_df = fdr.DataReader(stock_code, start_date, end_date)
                
            if price_df.empty:
                st.info("해당 기간의 주가 데이터가 없습니다.")
            else:
                st.subheader(f"{company_name_input} 주가 분석")
                
                # 이동평균선 계산
                price_df['MA5'] = price_df['Close'].rolling(5).mean()
                price_df['MA20'] = price_df['Close'].rolling(20).mean()
                price_df['MA60'] = price_df['Close'].rolling(60).mean()
                price_df['MA120'] = price_df['Close'].rolling(120).mean()

                # 차트 생성 (상단: 캔들/이평선, 하단: 거래량)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                    vertical_spacing=0.05, row_heights=[0.7, 0.3])

                # 캔들스틱 추가
                fig.add_trace(go.Candlestick(
                    x=price_df.index, open=price_df['Open'], high=price_df['High'],
                    low=price_df['Low'], close=price_df['Close'], name="주가",
                    increasing_line_color='red', decreasing_line_color='blue',
                    customdata=price_df['Volume'],
                    hovertemplate="<b>날짜: %{x}</b><br>종가: %{close:,.0f}원<br>거래량: %{customdata:,.0f}<extra></extra>"
                ), row=1, col=1)

                # 이평선 추가
                ma_info = [('MA5', 'green'), ('MA20', 'red'), ('MA60', 'orange'), ('MA120', 'purple')]
                for ma, color in ma_info:
                    fig.add_trace(go.Scatter(x=price_df.index, y=price_df[ma], name=ma, 
                                             line=dict(color=color, width=1), hoverinfo='skip'), row=1, col=1)

                # 거래량 차트 (상승/하락 색상 구분)
                vol_colors = ['red' if price_df.Open[i] < price_df.Close[i] else 'blue' for i in range(len(price_df))]
                fig.add_trace(go.Bar(x=price_df.index, y=price_df['Volume'], name="거래량", 
                                     marker_color=vol_colors, showlegend=False), row=2, col=1)

                fig.update_layout(height=700, template="plotly_white", xaxis_rangeslider_visible=False,
                                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                
                st.plotly_chart(fig, use_container_width=True)

                # 엑셀 다운로드
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    price_df.to_excel(writer, index=True, sheet_name='PriceData')
                st.download_button(
                    label="📥 주가 데이터 엑셀 다운로드",
                    data=output.getvalue(),
                    file_name=f"{company_name_input}_data.xlsx",
                    mime="application/vnd.ms-excel"
                )

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")