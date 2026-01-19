# 표준 라이브러리
import datetime
from io import BytesIO

# 서드파티 라이브러리
import datetime
from io import BytesIO
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import matplotlib.pyplot as plt
import koreanize_matplotlib

import os
from dotenv import load_dotenv
load_dotenv()
db_name = os.getenv('DB_NAME')
st.header(db_name)

def get_krx_company_list() -> pd.DataFrame:
    try:
        # 파이썬 및 인터넷의 기본 문자열 인코딩 방식- UTF-8
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        # MS 프로그램들은 cp949 / 구 몇몇 파일들의 인코딩 방식: EUC-KR
        df_listing = pd.read_html(url, header=0, flavor='bs4', encoding='EUC-KR')[0]
        
        # 필요한 컬럼만 추출 및 종목코드 6자리 포맷 맞추기
        df_listing = df_listing[['회사명', '종목코드']].copy()
        df_listing['종목코드'] = df_listing['종목코드'].apply(lambda x: f'{x:06}')
        return df_listing
    except Exception as e:
        st.error(f"상장사 명단을 불러오는 데 실패했습니다: {e}")
        return pd.DataFrame(columns=['회사명', '종목코드'])

def get_stock_code_by_company(company_name: str) -> str:
    # 만약 입력값이 숫자 6자리라면 그대로 반환
    if company_name.isdigit() and len(company_name) == 6:
        return company_name
    
    company_df = get_krx_company_list()
    codes = company_df[company_df['회사명'] == company_name]['종목코드'].values
    if len(codes) > 0:
        return codes[0]
    else:
        raise ValueError(f"'{company_name}'을 찾을 수 없습니다. 종목코드 6자리를 직접 입력해보세요.")

company_name = st.sidebar.text_input('조회할 회사를 입력하세요')
#  v수정

today = datetime.datetime.now()
jan_1 = datetime.date(today.year, 1, 1)
dec_31 = datetime.date(today.year, 12, 31)

selected_dates = st.sidebar.date_input(
    "조회하기",
    (jan_1, today),
    format="YYYY.MM.DD",
)


# --- [신규 추가] 시가총액 TOP 10 목록 및 클릭 이벤트 ---
st.sidebar.markdown("### 시가총액 TOP 10")

# 세션 상태 초기화 (클릭 시 자동 조회를 위함)
if 'company_name' not in st.session_state:
    st.session_state.company_name = ""
if 'auto_submit' not in st.session_state:
    st.session_state.auto_submit = False

@st.cache_data
def get_top_10_stocks():
    # 실시간 시가총액 순위 데이터 가져오기
    df = fdr.StockListing('KRX')
    top_10 = df.sort_values(by='Marcap', ascending=False).head(10)
    return top_10[['Name', 'Close', 'ChgRate']]

try:
    top_df = get_top_10_stocks()
    
    # 표 헤더 출력
    cols_header = st.sidebar.columns([2, 1, 1])
    cols_header[0].caption("주식명")
    cols_header[1].caption("종가")
    cols_header[2].caption("등락률")

# --- [신규 추가 및 보완] 시가총액 TOP 10 목록 ---
st.sidebar.markdown("### 시가총액 TOP 10")

# 세션 상태 초기화
if 'company_name' not in st.session_state:
    st.session_state.company_name = ""
if 'auto_submit' not in st.session_state:
    st.session_state.auto_submit = False

@st.cache_data(ttl=3600)  # 1시간 동안 결과 캐싱
def get_top_10_stocks():
    try:
        # KRX 상장사 전체 목록 (시가총액 포함)
        df = fdr.StockListing('KRX')
        # 시가총액 순 정렬 후 상위 10개 추출
        top_10 = df.sort_values(by='Marcap', ascending=False).head(10)
        return top_10[['Name', 'Close', 'ChgRate']]
    except Exception as e:
        # 에러 발생 시 빈 데이터프레임 반환하여 메인 로직 방해 방지
        return pd.DataFrame()

top_df = get_top_10_stocks()

if not top_df.empty:
    # 헤더
    h_cols = st.sidebar.columns([2, 1, 1])
    h_cols[0].caption("주식명")
    h_cols[1].caption("종가")
    h_cols[2].caption("등락률")

    for i, row in top_df.iterrows():
        cols = st.sidebar.columns([2, 1, 1])
        
        # 종목명 버튼 클릭 시 이벤트
        if cols[0].button(row['Name'], key=f"top_{i}"):
            st.session_state.company_name = row['Name']
            st.session_state.auto_submit = True
            st.rerun()
            
        # 수치 표시
        color = "red" if row['ChgRate'] > 0 else "blue" if row['ChgRate'] < 0 else "gray"
        cols[1].write(f"{int(row['Close']):,}")
        cols[2].markdown(f":{color}[{row['ChgRate']:.2f}%]")
else:
    st.sidebar.warning("목록을 불러오는 중입니다. 잠시 후 다시 시도해 주세요.")

st.sidebar.markdown("---")
# --- [신규 추가 끝] ---

confirm_btn = st.sidebar.button('조회하기') # 클릭하면 True


# --- 메인 로직 ---
if confirm_btn:
    if not company_name: # '' 
        st.warning("조회할 회사 이름을 입력하세요.")
    else:
        try:
            with st.spinner('데이터를 수집하는 중...'):
                stock_code = get_stock_code_by_company(company_name)
                start_date = selected_dates[0].strftime("%Y%m%d")
                end_date = selected_dates[1].strftime("%Y%m%d")
                
                price_df = fdr.DataReader(stock_code, start_date, end_date)
                
            if price_df.empty:
                st.info("해당 기간의 주가 데이터가 없습니다.")
            else:
                st.subheader(f"{company_name} 주가 데이터")
                st.dataframe(price_df.tail(10), width="stretch")

                # Matplotlib 시각화
                # fig, ax = plt.subplots(figsize=(12, 5))
                # price_df['Close'].plot(ax=ax, grid=True, color='red')
                # ax.set_title(f"{company_name} 종가 추이", fontsize=15)
                # st.pyplot(fig)

                # Plotly 시각화
                import plotly.graph_objects as go
                import streamlit as st

                # 1. 이동평균선 데이터 계산
                price_df['MA5'] = price_df['Close'].rolling(window=5).mean()
                price_df['MA20'] = price_df['Close'].rolling(window=20).mean()
                price_df['MA60'] = price_df['Close'].rolling(window=60).mean()
                price_df['MA120'] = price_df['Close'].rolling(window=120).mean()

                # 2. 기본 캔들스틱 차트 생성
                fig = go.Figure()

                # 캔들스틱 추가
                fig.add_trace(go.Candlestick(
                    x=price_df.index,
                    open=price_df['Open'],
                    high=price_df['High'],
                    low=price_df['Low'],
                    close=price_df['Close'],
                    name="주가",
                    increasing_line_color='#FF3333',
                    decreasing_line_color='#3333FF',
                    # 마우스 오버 시 표시될 텍스트 커스텀
                    customdata=price_df['Volume'],
                    hovertemplate="<b>날짜: %{x}</b><br>종가: %{close:,.0f}원<br>거래량: %{customdata:,.0f}<extra></extra>"
                ))

                # 3. 이동평균선 추가 (각각 다른 색상으로 설정)
                ma_list = [
                    ('MA5', 'green', '5일선'),
                    ('MA20', 'red', '20일선'),
                    ('MA60', 'orange', '60일선'),
                    ('MA120', 'purple', '120일선')
                ]

                for col, color, name in ma_list:
                    fig.add_trace(go.Scatter(
                        x=price_df.index, 
                        y=price_df[col], 
                        mode='lines',
                        line=dict(color=color, width=1),
                        name=name,
                        hoverinfo='skip' # 선 위에서는 툴팁이 안 뜨게 설정 (캔들 정보에 집중)
                    ))

                # 4. 레이아웃 설정
                fig.update_layout(
                    title=f"<b>{company_name} 주가 및 이동평균선</b>",
                    xaxis_title="날짜",
                    yaxis_title="가격",
                    height=600,
                    template="plotly_white",
                    xaxis_rangeslider_visible=False,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )

                # 5. 스트림릿 출력
                st.plotly_chart(fig, use_container_width=True)


                # 엑셀 다운로드 기능
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    price_df.to_excel(writer, index=True, sheet_name='Sheet1')
                st.download_button(
                    label="📥 엑셀 파일 다운로드",
                    data=output.getvalue(),
                    file_name=f"{company_name}_주가.xlsx",
                    mime="application/vnd.ms-excel"
                )
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")