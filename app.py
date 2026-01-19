import datetime
from io import BytesIO
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from dotenv import load_dotenv

# --- 설정 및 세션 초기화 ---
load_dotenv()
st.set_page_config(page_title="주가 데이터 분석", layout="wide")
st.header(os.getenv('DB_NAME', '주가 데이터 분석'))

today = datetime.date.today()

if 'start_date' not in st.session_state:
    st.session_state.start_date = datetime.date(today.year, 1, 1)
if 'company_name' not in st.session_state:
    st.session_state.company_name = ""
if 'auto_submit' not in st.session_state:
    st.session_state.auto_submit = False

# --- 데이터 획득 함수 ---
@st.cache_data(ttl=3600)
def get_fixed_top_10():
    stocks = {
        '삼성전자': '005930', 'SK하이닉스': '000660', 'LG에너지솔루션': '373220',
        '삼성바이오로직스': '207940', '현대차': '005380', '기아': '000270',
        '셀트리온': '068270', 'KB금융': '105560', 'NAVER': '035420', '신한지주': '055550'
    }
    results = []
    for name, code in stocks.items():
        try:
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
def get_krx_list():
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        df = pd.read_html(url, header=0, flavor='bs4', encoding='EUC-KR')[0]
        df = df[['회사명', '종목코드']].copy()
        df['종목코드'] = df['종목코드'].apply(lambda x: f'{x:06}')
        return df
    except:
        return pd.DataFrame(columns=['회사명', '종목코드'])

def get_code(name):
    if not name: return None
    if name.isdigit() and len(name) == 6:
        return name
    df = get_krx_list()
    codes = df[df['회사명'] == name]['종목코드'].values
    return codes[0] if len(codes) > 0 else None

# --- 사이드바 UI ---
company_name_input = st.sidebar.text_input(
    '조회할 회사를 입력하세요', 
    value=st.session_state.company_name,
    key="search_input"
)

st.sidebar.write("조회 기간 설정")
date_cols = st.sidebar.columns(4)
periods = [15, 30, 60, 120]
for i, p in enumerate(periods):
    if date_cols[i].button(f"{p}일"):
        if company_name_input:
            st.session_state.company_name = company_name_input
        st.session_state.start_date = today - datetime.timedelta(days=p)
        st.session_state.auto_submit = True
        st.rerun()

selected_dates = st.sidebar.date_input(
    "날짜 범위",
    (st.session_state.start_date, today),
    format="YYYY.MM.DD",
)

if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    st.session_state.start_date = selected_dates[0]

confirm_btn = st.sidebar.button('조회하기', use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### 주요 종목 10선")
st.sidebar.caption("주식명을 클릭하면 자동 검색됩니다.")

with st.sidebar:
    with st.spinner("주요 주식 10선 데이터 수집 중..."):
        top_df = get_fixed_top_10()

if not top_df.empty:
    cols_h = st.sidebar.columns([2, 1, 1])
    cols_h[0].caption("주식명")
    cols_h[1].caption("종가")
    cols_h[2].caption("등락")

    for i, row in top_df.iterrows():
        cols = st.sidebar.columns([2, 1, 1])
        if cols[0].button(row['Name'], key=f"btn_{i}"):
            st.session_state.company_name = row['Name']
            st.session_state.auto_submit = True
            st.rerun()
        
        if row['ChgRate'] > 0:
            color_str = f":red[{row['ChgRate']:.1f}%]"
        elif row['ChgRate'] < 0:
            color_str = f":blue[{row['ChgRate']:.1f}%]"
        else:
            color_str = f"{row['ChgRate']:.1f}%"
            
        cols[1].write(f"{int(row['Close']):,}")
        cols[2].markdown(color_str)

# --- 메인 분석 로직 ---
if confirm_btn or st.session_state.auto_submit:
    target = company_name_input if confirm_btn else st.session_state.company_name
    st.session_state.company_name = target
    st.session_state.auto_submit = False
    
    if target:
        code = get_code(target)
        if code:
            try:
                start_str = st.session_state.start_date.strftime("%Y%m%d")
                end_str = today.strftime("%Y%m%d")
                price_df = fdr.DataReader(code, start_str, end_str)
                
                if not price_df.empty:
                    st.subheader(f"{target} 분석 결과")
                    
                    # --- 수정 포인트: 전체 데이터 로드 및 스크롤 설정 ---
                    st.write("전체 데이터 내역 (스크롤 가능)")
                    # height를 지정하면 해당 높이를 넘을 경우 자동으로 내부 스크롤이 생깁니다.
                    st.dataframe(price_df.sort_index(ascending=False), use_container_width=True, height=300)

                    # 지표 계산
                    for n in [5, 20, 60, 120]:
                        price_df[f'MA{n}'] = price_df['Close'].rolling(n).mean()

                    # 차트 생성
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                        vertical_spacing=0.05, row_heights=[0.7, 0.3])

                    fig.add_trace(go.Candlestick(
                        x=price_df.index, open=price_df['Open'], high=price_df['High'],
                        low=price_df['Low'], close=price_df['Close'], name="캔들",
                        increasing_line_color='red', decreasing_line_color='blue'
                    ), row=1, col=1)

                    for ma, color in [('MA5', 'green'), ('MA20', 'red'), ('MA60', 'orange'), ('MA120', 'purple')]:
                        fig.add_trace(go.Scatter(x=price_df.index, y=price_df[ma], name=ma, 
                                                 line=dict(color=color, width=1)), row=1, col=1)

                    v_colors = ['red' if price_df.Open[i] < price_df.Close[i] else 'blue' for i in range(len(price_df))]
                    fig.add_trace(go.Bar(x=price_df.index, y=price_df['Volume'], name="거래량", 
                                         marker_color=v_colors), row=2, col=1)

                    # 빈 공간 제거
                    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
                    all_days = pd.date_range(start=price_df.index[0], end=price_df.index[-1])
                    holidays = all_days.difference(price_df.index)
                    fig.update_xaxes(rangebreaks=[dict(values=holidays)])

                    fig.update_layout(height=600, template="plotly_white", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

                    out = BytesIO()
                    with pd.ExcelWriter(out, engine='openpyxl') as w:
                        price_df.to_excel(w, index=True)
                    st.download_button("📥 엑셀 파일 다운로드", out.getvalue(), f"{target}.xlsx")
                else:
                    st.info("데이터가 없습니다.")
            except Exception as e:
                st.error(f"데이터 조회 중 오류 발생: {e}")
        else:
            st.error("종목 코드를 찾을 수 없습니다.")
    else:
        st.warning("회사명을 입력하세요.")