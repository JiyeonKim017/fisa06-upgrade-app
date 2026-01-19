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

# --- 1. 세션 상태 초기화 (클릭 이벤트 처리용) ---
if 'company_name' not in st.session_state:
    st.session_state.company_name = ""
if 'auto_submit' not in st.session_state:
    st.session_state.auto_submit = False

# --- 2. 데이터 관련 함수 ---
@st.cache_data(ttl=600)  # 10분마다 갱신하여 서버 부하 감소
def get_top_10_stocks():
    """시가총액 상위 10개 종목을 안정적으로 가져옵니다."""
    try:
        # KRX 전체 종목 리스트 가져오기
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            # 시가총액(Marcap) 기준으로 내림차순 정렬
            top_10 = df.sort_values(by='Marcap', ascending=False).head(10)
            return top_10[['Name', 'Close', 'ChgRate']]
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

@st.cache_data
def get_krx_company_list() -> pd.DataFrame:
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        df_listing = pd.read_html(url, header=0, flavor='bs4', encoding='EUC-KR')[0]
        df_listing = df_listing[['회사명', '종목코드']].copy()
        df_listing['종목코드'] = df_listing['종목코드'].apply(lambda x: f'{x:06}')
        return df_listing
    except:
        return pd.DataFrame(columns=['회사명', '종목코드'])

def get_stock_code_by_company(company_name: str) -> str:
    if company_name.isdigit() and len(company_name) == 6:
        return company_name
    company_df = get_krx_company_list()
    codes = company_df[company_df['회사명'] == company_name]['종목코드'].values
    if len(codes) > 0:
        return codes[0]
    else:
        raise ValueError(f"'{company_name}'을 찾을 수 없습니다.")

# --- 3. 사이드바 UI 구성 (순서 조정) ---

# (A) 입력창 및 날짜 설정
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

# (B) 조회하기 버튼
confirm_btn = st.sidebar.button('조회하기', use_container_width=True)

st.sidebar.markdown("---")

# (C) 시가총액 TOP 10 (요청대로 버튼 하단에 배치)
st.sidebar.markdown("### 시가총액 TOP 10")
top_df = get_top_10_stocks()

if not top_df.empty:
    h_cols = st.sidebar.columns([2, 1, 1])
    h_cols[0].caption("주식명")
    h_cols[1].caption("종가")
    h_cols[2].caption("등락률")

    for i, row in top_df.iterrows():
        cols = st.sidebar.columns([2, 1, 1])
        # 클릭 시 세션 업데이트 및 즉시 조회
        if cols[0].button(row['Name'], key=f"top_btn_{i}"):
            st.session_state.company_name = row['Name']
            st.session_state.auto_submit = True
            st.rerun()
            
        color = "red" if row['ChgRate'] > 0 else "blue" if row['ChgRate'] < 0 else "white"
        cols[1].write(f"{int(row['Close']):,}")
        cols[2].markdown(f":{color}[{row['ChgRate']:.2f}%]")
else:
    # 데이터 로딩 실패 시 안내 문구
    st.sidebar.info("데이터 서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.")


# --- 4. 메인 분석 로직 ---
if confirm_btn or st.session_state.auto_submit:
    st.session_state.auto_submit = False  # 자동 실행 상태 초기화
    
    if not company_name_input:
        st.warning("조회할 회사 이름을 입력하세요.")
    else:
        try:
            with st.spinner('데이터를 불러오는 중...'):
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

                # 캔들스틱 + 거래량 차트 생성
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                    vertical_spacing=0.05, row_heights=[0.7, 0.3])

                # 캔들스틱 차트
                fig.add_trace(go.Candlestick(
                    x=price_df.index, open=price_df['Open'], high=price_df['High'],
                    low=price_df['Low'], close=price_df['Close'], name="주가",
                    increasing_line_color='red', decreasing_line_color='blue',
                    customdata=price_df['Volume'],
                    hovertemplate="<b>날짜: %{x}</b><br>종가: %{close:,.0f}원<br>거래량: %{customdata:,.0f}<extra></extra>"
                ), row=1, col=1)

                # 이평선 추가
                ma_styles = [('MA5', 'green'), ('MA20', 'red'), ('MA60', 'orange'), ('MA120', 'purple')]
                for ma, color in ma_styles:
                    fig.add_trace(go.Scatter(x=price_df.index, y=price_df[ma], name=ma, 
                                             line=dict(color=color, width=1.2), hoverinfo='skip'), row=1, col=1)

                # 거래량 차트 (양봉/음봉 색상 연동)
                vol_colors = ['red' if price_df.Open[i] < price_df.Close[i] else 'blue' for i in range(len(price_df))]
                fig.add_trace(go.Bar(x=price_df.index, y=price_df['Volume'], name="거래량", 
                                     marker_color=vol_colors, showlegend=False), row=2, col=1)

                fig.update_layout(height=800, template="plotly_white", xaxis_rangeslider_visible=False,
                                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                
                st.plotly_chart(fig, use_container_width=True)

                # 엑셀 다운로드 기능
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    price_df.to_excel(writer, index=True, sheet_name='PriceData')
                st.download_button(
                    label="📥 주가 데이터 엑셀 다운로드",
                    data=output.getvalue(),
                    file_name=f"{company_name_input}_주가데이터.xlsx",
                    mime="application/vnd.ms-excel"
                )

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")