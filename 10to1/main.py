import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # DON'T CHANGE THIS !!!

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from fpdf import FPDF
import re
import uuid
import glob
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
from werkzeug.utils import secure_filename
import json
import shutil
import numpy as np
from datetime import datetime
import matplotlib.gridspec as gridspec

app = Flask(__name__)
application = app

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['RESULTS_FOLDER'] = os.path.join(os.path.dirname(__file__), 'results')
app.config['IMAGES_FOLDER'] = os.path.join(os.path.dirname(__file__), 'images')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'jpg', 'jpeg', 'png'}
app.config['MAX_IMAGES'] = 3  # 최대 이미지 업로드 개수

# 글로벌 에러 핸들러 추가 - 모든 서버 에러를 JSON으로 반환
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f"Unhandled exception: {str(e)}")
    app.logger.exception("Exception details:")
    return jsonify({
        'status': 'error',
        'message': f"서버 오류가 발생했습니다: {str(e)}"
    }), 500

def setup_font_once():
    font_path = './static/NanumGothic.ttf'
    if not any(f.name == 'NanumGothic' for f in fm.fontManager.ttflist):
        fe = fm.FontEntry(fname=font_path, name='NanumGothic')
        fm.fontManager.ttflist.insert(0, fe)
    plt.rcParams['font.family'] = 'NanumGothic'
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['figure.dpi'] = 100
    plt.rcParams['savefig.dpi'] = 300

setup_font_once() 

# 폰트 파일 등록 (한 번만 실행)
fe = fm.FontEntry(
    fname='./static/NanumGothic.ttf',  # 상대 경로 사용
    name='NanumGothic')
# 폰트 매니저에 폰트 추가 (한 번만 실행)
fm.fontManager.ttflist.insert(0, fe)
# Matplotlib의 기본 폰트 변경 (한 번만 설정)
plt.rcParams['font.family'] = fe.name
plt.rcParams['axes.unicode_minus'] = False

# font_path = os.path.join(os.path.dirname(__file__), 'static', 'NanumGothic.ttf')
# font_prop = fm.FontProperties(fname=font_path)
# plt.rcParams['font.family'] = font_prop.get_name()
# plt.rcParams['axes.unicode_minus'] = False
# plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['figure.dpi'] = 100
plt.rcParams['savefig.dpi'] = 300  # 고해상도 이미지 저장

# 파일 확장자 확인 함수
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# 날짜 형식 변환 함수
def format_date_korean(date_str):
    if pd.isna(date_str) or not date_str:
        return "날짜 정보 없음"
    try:
        if isinstance(date_str, str) and re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', date_str):
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return f"{date_obj.year}년 {date_obj.month}월 {date_obj.day}일"
        date_patterns = ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y.%m.%d %H:%M:%S']
        for pattern in date_patterns:
            try:
                date_obj = datetime.strptime(str(date_str), pattern)
                return f"{date_obj.year}년 {date_obj.month}월 {date_obj.day}일"
            except:
                continue
        numbers = re.findall(r'\d+', str(date_str))
        if len(numbers) >= 3:
            year = numbers[0]
            if len(year) == 2: year = '20' + year if int(year) < 50 else '19' + year
            month = numbers[1].zfill(2)
            day = numbers[2].zfill(2)
            return f"{year}년 {int(month)}월 {int(day)}일"
    except:
        pass
    return str(date_str)

# 데이터 정제 함수들 (기존과 동일)
def load_and_prepare(file_path, rename_dict):
    try:
        df_raw = pd.read_excel(file_path)
        if df_raw.shape[0] < 3: raise ValueError("엑셀 파일의 데이터가 충분하지 않습니다. 최소 3행 이상의 데이터가 필요합니다.")
        if 'Unnamed: 0' in df_raw.columns and 'Unnamed: 1' in df_raw.columns:
            second_row = df_raw.iloc[1].tolist()
            if '자료제목' in second_row or '조사날짜' in second_row:
                df_raw.columns = df_raw.iloc[1]
                df_raw = df_raw.iloc[2:].reset_index(drop=True)
            else:
                for i in range(min(5, df_raw.shape[0])):
                    row_values = df_raw.iloc[i].tolist()
                    if '자료제목' in row_values or '조사날짜' in row_values:
                        df_raw.columns = df_raw.iloc[i]
                        df_raw = df_raw.iloc[i+1:].reset_index(drop=True)
                        break
        required_columns = ['조사날짜', '시군(지역주소)', '고유지역(해안)명', '참가자 수(단위: 명)']
        missing_columns = [col for col in required_columns if col not in df_raw.columns]
        if missing_columns: raise ValueError(f"필수 컬럼이 누락되었습니다: {', '.join(missing_columns)}")
        return df_raw.rename(columns=rename_dict)
    except Exception as e:
        raise ValueError(f"엑셀 파일 로드 중 오류가 발생했습니다: {str(e)}")

def extract_time_from_row(row):
    try:
        s = str(row.get('조사날짜', ''))
        m = re.search(r'(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})', s)
        if m: return pd.Series([m.group(1), m.group(2)])
        s = str(row.get('조사시간', ''))
        m = re.search(r'(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})', s)
        if m: return pd.Series([m.group(1), m.group(2)])
    except Exception as e:
        print(f"시간 추출 오류: {str(e)}")
    return pd.Series([None, None])

def extract_date(dt):
    if pd.isna(dt): return None
    m = re.match(r'([0-9]{4})[.\-\s]*([0-9]{1,2})[.\-\s]*([0-9]{1,2})', str(dt))
    if m: y, mth, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2); return f"{y}-{mth}-{d}"
    return dt

def extract_lat_lon(loc):
    if pd.isna(loc): return pd.Series([None, None])
    parts = re.findall(r"[-+]?\d*\.\d+|\d+", str(loc))
    if len(parts) >= 2: return pd.Series([float(parts[0]), float(parts[1])])
    return pd.Series([None, None])

def parse_campaign_items(txt, item_cols):
    results = {k: 0 for k in item_cols}
    if pd.isna(txt): return pd.Series(results)
    for line in str(txt).split('\n'):
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:  # 안전하게 처리
                key, val = parts
                key, val = key.strip(), re.sub(r'[^\d]', '', val)
                if key in results and val != '':
                    try: results[key] = int(val)
                    except ValueError: results[key] = 0
    return pd.Series(results)

def remove_unit(val):
    if pd.isna(val): return 0
    try:
        m = re.search(r'(\d+(\.\d+)?)', str(val))
        return float(m.group(1)) if m else 0
    except (ValueError, TypeError): return 0

def shorten_item_name(name):
    short_names = {
        '스티로폼 부표': '스티로폼', '어업용 밧줄': '밧줄', '페트병(병과 뚜껑, 음료용)': '페트병',
        '식품포장용 비닐(커피포장, 라면봉지, 과자봉지 등)': '식품비닐', '비닐봉지': '비닐봉지',
        '낚시쓰레기(낚싯줄, 바늘, 추, 천평, 가짜미끼, 낚시용품 비닐포장 등)': '낚시쓰레기', '담배 꽁초': '담배꽁초',
        '폭죽쓰레기(연발 폭죽 화약피, 스파클러 철사, 로망캔들 종이막대 등)': '폭죽쓰레기',
        '플라스틱 노끈(양식업용 또는 포장용)': '플라스틱노끈', '장어통발': '장어통발', '기타': '기타쓰레기'
    }
    return short_names.get(name, name)

def clean_data(file_path):
    try:
        rename_dict = {
            '자료제목': '자료제목', '조사날짜': '조사날짜', '시군(지역주소)': '시군(지역주소)',
            '고유지역(해안)명': '고유지역(해안)명', '공동 조사자': '공동 조사자',
            '조사한 쓰레기의 무게(저울이 있는 경우, kg 단위로 측정하여 합계한 무게를 기록) (단위: kg)': '수거무게(kg)',
            '조사한 해안선의 길이(단위: m)': '조사한 해안선 길이 (m)',
            '전체 청소한 해안선의 길이(단위: m)(선택)': '전체 청소한 해안선 길이 (m)',
            '참가자 수(단위: 명)': '참가자 수 (명)',
            '수거한 쓰레기 봉투수(20리터 기준) (단위: 개(봉투))': '수거봉투 수 (20L)',
            '수거한 쓰레기 봉투수(20리터 기준)': '수거봉투 수 (20L)', '조사시간': '조사시간'
        }
        df = load_and_prepare(file_path, rename_dict)
        
        # 시간 추출 오류 수정 - 안전하게 처리
        try:
            df[['조사 시작시간', '조사 종료시간']] = df.apply(extract_time_from_row, axis=1)
        except Exception as e:
            print(f"시간 추출 중 오류 발생: {str(e)}")
            df['조사 시작시간'] = None
            df['조사 종료시간'] = None
            
        df['조사날짜'] = df['조사날짜'].apply(extract_date)
        
        # 위도/경도 추출 오류 수정 - 안전하게 처리
        try:
            if '조사위치' in df.columns: 
                df[['위도', '경도']] = df['조사위치'].apply(extract_lat_lon)
            else: 
                df['위도'] = None
                df['경도'] = None
        except Exception as e:
            print(f"위치 추출 중 오류 발생: {str(e)}")
            df['위도'] = None
            df['경도'] = None
            
        item_cols = [
            '스티로폼 부표', '어업용 밧줄', '페트병(병과 뚜껑, 음료용)',
            '식품포장용 비닐(커피포장, 라면봉지, 과자봉지 등)', '비닐봉지',
            '낚시쓰레기(낚싯줄, 바늘, 추, 천평, 가짜미끼, 낚시용품 비닐포장 등)', '담배 꽁초',
            '폭죽쓰레기(연발 폭죽 화약피, 스파클러 철사, 로망캔들 종이막대 등)', '플라스틱 노끈(양식업용 또는 포장용)',
            '장어통발', '기타'
        ]
        
        # 항목 추출 오류 수정 - 안전하게 처리
        try:
            if '열일캠페인의 10가지 항목 조사' in df.columns:
                df[item_cols] = df['열일캠페인의 10가지 항목 조사'].apply(lambda x: parse_campaign_items(x, item_cols))
            else: 
                for col in item_cols: df[col] = 0
        except Exception as e:
            print(f"항목 추출 중 오류 발생: {str(e)}")
            for col in item_cols: df[col] = 0
            
        unit_cols = ['수거무게(kg)', '조사한 해안선 길이 (m)', '전체 청소한 해안선 길이 (m)', '참가자 수 (명)', '수거봉투 수 (20L)']
        for col in unit_cols:
            if col in df.columns: df[col] = df[col].apply(remove_unit)
            else: df[col] = 0
        final_cols = ['자료제목', '조사날짜', '시군(지역주소)', '고유지역(해안)명', '공동 조사자', '수거무게(kg)'] + item_cols + [
            '조사한 해안선 길이 (m)', '전체 청소한 해안선 길이 (m)', '참가자 수 (명)', '수거봉투 수 (20L)',
            '조사 시작시간', '조사 종료시간', '위도', '경도'
        ]
        for col in final_cols:
            if col not in df.columns:
                if col in ['수거무게(kg)', '조사한 해안선 길이 (m)', '전체 청소한 해안선 길이 (m)', '참가자 수 (명)', '수거봉투 수 (20L)'] + item_cols:
                    df[col] = 0
                else: df[col] = None
        numeric_cols = ['수거무게(kg)', '조사한 해안선 길이 (m)', '전체 청소한 해안선 길이 (m)', '참가자 수 (명)', '수거봉투 수 (20L)'] + item_cols
        for col in numeric_cols:
            df[col] = df[col].fillna(0)
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df_final = df[final_cols]
        return df_final
    except Exception as e:
        raise ValueError(f"데이터 정제 중 오류가 발생했습니다: {str(e)}")

# 데이터 분석 및 시각화 함수 (개별 파일 분석용)
def analyze_single_data(df, session_id, file_index):
    try:
        item_cols = [
            '스티로폼 부표', '어업용 밧줄', '페트병(병과 뚜껑, 음료용)', '식품포장용 비닐(커피포장, 라면봉지, 과자봉지 등)',
            '비닐봉지', '낚시쓰레기(낚싯줄, 바늘, 추, 천평, 가짜미끼, 낚시용품 비닐포장 등)', '담배 꽁초',
            '폭죽쓰레기(연발 폭죽 화약피, 스파클러 철사, 로망캔들 종이막대 등)', '플라스틱 노끈(양식업용 또는 포장용)', '장어통발', '기타'
        ]
        for col in item_cols: 
            if col not in df.columns: df[col] = 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        short_names = {col: shorten_item_name(col) for col in item_cols}
        item_data = {short_names[col]: float(df.loc[0, col]) for col in item_cols}
        item_counts = pd.Series(item_data)
        
        results_path = os.path.join(app.config['RESULTS_FOLDER'], session_id)
        os.makedirs(results_path, exist_ok=True)
        
        # 파일별 고유 식별자 추가
        file_prefix = f"file{file_index}_";
        
        # 항목별 수거 현황 그래프
        plt.figure(figsize=(12, 6))
        # 개수가 많은 항목부터 왼쪽에 표시되도록 내림차순 정렬
        sorted_item_counts = item_counts.sort_values(ascending=False)
        ax = sorted_item_counts.plot(kind='bar', color='#0d6efd')
        plt.title(f'항목별 수거 개수', fontsize=16)
        plt.ylabel('개수', fontsize=12); plt.xlabel('항목', fontsize=12)
        plt.xticks(rotation=45, ha='right')
        for i, v in enumerate(sorted_item_counts): ax.text(i, v + 0.2, str(int(v)), ha='center', fontsize=10)
        plt.tight_layout()
        bar_items_path = os.path.join(results_path, f'{file_prefix}bar_items.png')
        plt.savefig(bar_items_path, dpi=300); plt.close()
        
        # Top 3 수거 항목
        plt.figure(figsize=(8, 5))
        top_n = item_counts.sort_values(ascending=False).head(3)
        if not top_n.empty:
            ax = top_n.plot(kind='bar', color='tomato')
            plt.title(f'Top 3 수거 항목', fontsize=16)
            plt.ylabel('개수', fontsize=12)
            for i, v in enumerate(top_n): ax.text(i, v + 0.5, str(int(v)), ha='center', fontsize=10)
            plt.xticks(rotation=30, ha='right')
        else: plt.text(0.5, 0.5, '데이터 없음', ha='center', va='center')
        plt.tight_layout()
        top_items_path = os.path.join(results_path, f'{file_prefix}top_items.png')
        plt.savefig(top_items_path, dpi=300); plt.close()
        
        # 항목별 비율 파이 그래프 (라벨 바깥쪽에 직접 표시)
        plt.figure(figsize=(12, 8))
        total = item_counts.sum()
        if total > 0:
            non_zero_items = item_counts[item_counts > 0]
            if len(non_zero_items) > 0:
                percentages = (non_zero_items / total * 100)
                
                # 작은 비율 항목 처리 (예: 2% 미만은 '그 외'로 묶기)
                threshold = 2.0
                small_slices = percentages[percentages < threshold]
                main_slices = percentages[percentages >= threshold]
                
                if not small_slices.empty:
                    main_slices['그 외'] = small_slices.sum()
                    percentages_to_plot = main_slices.sort_values(ascending=False)
                else:
                    percentages_to_plot = percentages.sort_values(ascending=False)
                
                # 라벨 생성 (항목명과 퍼센트 함께 표시)
                labels = [f'{name}({p:.1f}%)' for name, p in percentages_to_plot.items()]
                
                # 파이 그래프 생성 (라벨을 바깥쪽에 직접 표시)
                pie_return = plt.pie(
                    percentages_to_plot,
                    startangle=90,
                    shadow=False,
                    labels=labels,  # 라벨 직접 표시
                    autopct='',  # 자동 퍼센트 표시 비활성화
                    wedgeprops={'edgecolor': 'white', 'linewidth': 1},
                    textprops={'fontsize': 11},
                    labeldistance=1.1  # 라벨 위치를 바깥쪽으로 조정
                )
                # plt.pie 반환값은 autopct 옵션에 따라 달라질 수 있으므로 안전하게 처리
                wedges = pie_return[0]  # wedges는 항상 첫 번째 요소
                
                plt.axis('equal')
                plt.title(f'항목별 비율 (%)', fontsize=16, pad=20)
                
                
            else: plt.text(0.5, 0.5, '데이터 없음', ha='center', va='center')
        else: plt.text(0.5, 0.5, '데이터 없음', ha='center', va='center')
        plt.tight_layout()
        pie_chart_path = os.path.join(results_path, f'{file_prefix}pie_chart.png')
        plt.savefig(pie_chart_path, dpi=300); plt.close()
        
        # 결론 및 제언 생성
        top_items = item_counts.sort_values(ascending=False).head(3)
        top_items_str = ', '.join([f"{name} ({int(count)}개)" for name, count in top_items.items()])
        
        conclusion = {
            'summary': f"이번 연안정화활동에서는 총 {int(df.loc[0, '참가자 수 (명)']):,}명의 참가자가 {float(df.loc[0, '전체 청소한 해안선 길이 (m)']):,.1f}m의 해안선을 청소하여 {float(df.loc[0, '수거무게(kg)']):,.1f}kg의 쓰레기를 수거했습니다.",
            'top_items': f"가장 많이 수거된 항목은 {top_items_str}로, 이는 해당 지역의 주요 오염원으로 볼 수 있습니다. 향후 이러한 항목들의 발생을 줄이기 위한 예방 활동과 인식 개선이 필요합니다.",
            'recommendation': "정기적인 연안정화활동을 통해 해안 환경을 지속적으로 관리하고, 수거된 쓰레기의 분석 결과를 환경 정책 수립에 반영한다면 더 효과적인 해양 환경 보전이 가능할 것입니다."
        }
        
        # 지역명 추출 (파일명으로 사용)
        location = f"{df.loc[0, '시군(지역주소)']} {df.loc[0, '고유지역(해안)명']}"
        if pd.isna(location) or location.strip() == '':
            location = "지역명 없음"
        
        # 분석 결과 저장
        analysis_result = {
            'file_index': file_index,
            'original_filename': df.attrs.get('original_filename', f'파일 {file_index}'),
            'location': location,  # 지역명 추가
            'basic_info': {
                '조사 날짜': format_date_korean(df.loc[0, '조사날짜']),
                '지역': location,
                '수거 무게(kg)': float(df.loc[0, '수거무게(kg)']),
                '참가자 수(명)': int(df.loc[0, '참가자 수 (명)']),
                '수거 봉투 수(20L)': int(df.loc[0, '수거봉투 수 (20L)']),
                '청소한 해안선 길이(m)': float(df.loc[0, '전체 청소한 해안선 길이 (m)'])
            },
            'item_counts': {k: int(v) for k, v in item_counts.to_dict().items()},
            'item_full_names': {short_names[col]: col for col in item_cols},
            'images': {
                'bar_items': f'{file_prefix}bar_items.png',
                'top_items': f'{file_prefix}top_items.png',
                'pie_chart': f'{file_prefix}pie_chart.png'
            },
            'conclusion': conclusion  # 결론 및 제언 추가
        }
        return analysis_result
    except Exception as e:
        raise ValueError(f"데이터 분석 중 오류가 발생했습니다 (파일 {file_index}): {str(e)}")

# PDF 보고서 생성 함수 (다중 분석 결과 처리)

def generate_pdf_report(all_analysis_results, session_id, image_files=None):
    try:
        font_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'NanumGothic.ttf')
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"폰트 파일이 존재하지 않습니다: {font_path}")

        class PDF(FPDF):
            font_registered = False

            def __init__(self):
                super().__init__()
                if not PDF.font_registered:
                    self.add_font("Nanum", "", font_path, uni=True)
                    self.add_font("Nanum", "B", font_path, uni=True)
                    PDF.font_registered = True
                
            def header(self):
                self.set_font('Nanum', 'B', 24)
                self.set_text_color(0, 109, 239)
                self.cell(0, 15, '열일바다청소 분석 보고서', ln=True, align='C')
                self.set_font('Nanum', '', 10)
                self.set_text_color(128, 128, 128)
                self.cell(0, 5, f"생성일: {datetime.now().strftime('%Y년 %m월 %d일')}", ln=True, align='R')
                self.set_draw_color(0, 109, 239)
                self.set_line_width(0.5)
                self.line(15, 30, 195, 30)
                self.ln(10)

            def footer(self):
                self.set_y(-15)
                self.set_font('Nanum', '', 8)
                self.set_text_color(128, 128, 128)
                self.cell(0, 10, f'페이지 {self.page_no()}/{{nb}}', align='C')

            def section_title(self, title, subtitle=None):
                self.set_font('Nanum', 'B', 16)
                self.set_text_color(0, 109, 239)
                self.cell(0, 10, title, ln=True, align='L')  
                if subtitle:
                    self.set_font('Nanum', '', 12)
                    self.set_text_color(128, 128, 128)
                    self.cell(0, 6, subtitle, ln=True, align='L') 
                self.ln(2)


            def section_text(self, text):
                self.set_font('Nanum', '', 11)
                self.set_text_color(0, 0, 0)
                self.multi_cell(0, 6, text, align='L')  # ← 중앙 정렬 적용
                self.ln(2)

                
            def info_table(self, data):
                self.set_font('Nanum', '', 11)
                self.set_text_color(0, 0, 0)
                self.set_fill_color(240, 240, 240)
                
                col_width = 85
                row_height = 8
                table_width = col_width * 2
                table_x = (self.w - table_width) / 2  # ← 중앙 기준

                for key, value in data.items():
                    self.set_xy(table_x, self.get_y())  # ← 중앙 시작
                    self.set_font('Nanum', 'B', 11)
                    self.cell(col_width, row_height, key, border=1, fill=True)
                    self.set_font('Nanum', '', 11)
                    self.cell(col_width, row_height, str(value), border=1, ln=True)
                self.ln(5)

                
            def image_centered(self, img_path, w=150, caption=None):
                results_path = os.path.join(app.config['RESULTS_FOLDER'], session_id)
                full_img_path = os.path.join(results_path, img_path)
                if os.path.exists(full_img_path):
                    # 이미지 가로 중앙 정렬
                    page_width = self.w - 2 * self.l_margin  # usable width
                    img_x = (self.w - w) / 2  # 페이지 기준
                    self.image(full_img_path, x=img_x, w=w)
                    if caption:
                        self.set_font('Nanum', '', 10)
                        self.set_text_color(128, 128, 128)
                        self.cell(0, 6, caption, ln=True, align='C')  # 중앙 정렬 캡션
                    self.ln(6)
                else:
                    self.set_font('Nanum', '', 12)
                    self.cell(0, 10, f'이미지({os.path.basename(img_path)})를 찾을 수 없습니다', ln=True, align='C')
                    self.ln(6)

                    
            def items_table(self, item_counts, item_full_names):
                # 표 제목은 파란색
                self.set_font('Nanum', 'B', 12)
                self.set_text_color(0, 0, 0) 
                self.cell(0, 8, "항목별 수거 개수", ln=True, align='C')
                self.set_text_color(0, 0, 0) 
                
                # 표 컬럼 너비 설정
                col1_width = 130
                col2_width = 45
                table_width = col1_width + col2_width
                table_x = (self.w - table_width) / 2

                # 헤더 설정 (회색 배경 + 검정 텍스트)
                self.set_fill_color(240, 240, 240)
                self.set_text_color(0, 0, 0)  # ✅ 글씨 색 복원
                self.set_font('Nanum', 'B', 10)

                self.set_x(table_x)
                self.cell(col1_width, 8, "항목명", border=1, fill=True)
                self.cell(col2_width, 8, "수거 개수", border=1, ln=True, align='C', fill=True)  # ✅ fill=True 추가

                # 내용 출력
                sorted_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)
                self.set_font('Nanum', '', 10)
                for short_name, count in sorted_items:
                    full_name = item_full_names.get(short_name, short_name)
                    self.set_x(table_x)
                    self.cell(col1_width, 8, full_name, border=1)
                    self.cell(col2_width, 8, str(count), border=1, ln=True, align='C')
                self.ln(5)



                
            def conclusion_section(self, conclusion_data):
                self.set_font('Nanum', '', 11)
                self.set_text_color(0, 0, 0)
                self.multi_cell(0, 6, conclusion_data['summary'])
                self.ln(2)
                
                self.multi_cell(0, 6, conclusion_data['top_items'])
                self.ln(2)
                
                self.multi_cell(0, 6, conclusion_data['recommendation'])
                self.ln(5)

        pdf = PDF()
        pdf.alias_nb_pages()
        pdf.add_page()

        
        # 각 파일별 분석 결과 출력
        for idx, analysis_result in enumerate(all_analysis_results):
            if idx > 0:
                pdf.add_page() # 각 파일 분석 시작 시 새 페이지
            
                # 번호 리셋
            section_number = 1
            
            file_id = analysis_result['file_index']
            location = analysis_result['location']  # 지역명 사용
            
            # 파일별 제목
            pdf.set_font('Nanum', 'B', 18)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(0, 12, f"분석 결과: {location}", ln=True, align='L')
            pdf.ln(5)
            
            # 기본정보 섹션
            pdf.section_title(f'{section_number}. 기본정보')
            section_number += 1
            
            info_data = {
                "조사 날짜": analysis_result['basic_info']['조사 날짜'],
                "지역": analysis_result['basic_info']['지역'],
                "수거 무게(kg)": f"{analysis_result['basic_info']['수거 무게(kg)']:.1f}",
                "참가자 수(명)": str(analysis_result['basic_info']['참가자 수(명)']),
                "수거 봉투 수(20L)": str(analysis_result['basic_info']['수거 봉투 수(20L)']),
                "청소한 해안선 길이(m)": f"{analysis_result['basic_info']['청소한 해안선 길이(m)']:.1f}"
            }
            pdf.info_table(info_data)

            # 항목별 수거 현황
            pdf.add_page()
            pdf.section_title(f'{section_number}. 항목별 수거 현황', f'{location} 항목별 분석')
            section_number += 1
            pdf.section_text("수거된 쓰레기를 항목별로 분석한 결과입니다.")
            pdf.image_centered(analysis_result['images']['bar_items'], w=180, caption=f"그림 {idx*3+1}. 항목별 수거 개수")
            pdf.items_table(analysis_result['item_counts'], analysis_result['item_full_names'])

            # 항목별 비율 (파이 차트)
            pdf.add_page()
            pdf.section_title(f'{section_number}. 항목별 비율 분석', f'{location} 구성비')
            section_number += 1
            pdf.section_text("전체 수거된 쓰레기 중 각 항목이 차지하는 비율입니다.")
            pdf.ln(6) 
            pdf.image_centered(analysis_result['images']['pie_chart'], w=200, caption=f"그림 {idx*3+2}. 항목별 비율 분석")
            
            # 결론 및 제언 섹션 추가 (중복 제목 제거)
            pdf.add_page()
            pdf.section_title(f'{section_number}. 결론', f'{location}')
            pdf.conclusion_section(analysis_result['conclusion'])

        # 업로드된 이미지가 있는 경우 추가 (보고서 마지막에 한번만)
        if image_files and len(image_files) > 0:
            pdf.add_page()
            pdf.section_title(f'{len(all_analysis_results)*4+1}. 현장 사진')
            images_path = os.path.join(app.config['IMAGES_FOLDER'], session_id)
            for i, img_file in enumerate(image_files):
                if i > 0 and i % 2 == 0: pdf.add_page()
                img_path = os.path.join(images_path, img_file)
                if os.path.exists(img_path):
                    pdf.image(img_path, x=(210-160)/2, w=150)
                    pdf.set_font('Nanum', '', 10); pdf.set_text_color(128, 128, 128)
                    pdf.ln(0.3) 
                    pdf.cell(0, 6, f"사진 {i+1}. 연안정화활동 현장 인증사진", ln=True, align='C')
                    pdf.ln(6)

        # # 마무리 메시지
        # pdf.add_page()
        # pdf.set_font('Nanum', 'B', 12)
        # pdf.set_text_color(0, 109, 239)
        # pdf.cell(0, 10, "열일바다청소  분석 보고서 생성이 완료되었습니다.", ln=True, align='C')
        # pdf.ln(5)
        # pdf.set_font('Nanum', '', 11)
        # pdf.set_text_color(0, 0, 0)
        # pdf.multi_cell(0, 6, "본 보고서는 업로드된 각 엑셀 파일의 데이터를 개별적으로 분석한 결과를 포함하고 있습니다. "
        #                    "연안정화활동에 참여해주신 모든 분들께 감사드립니다.")

        # PDF 저장
        results_path = os.path.join(app.config['RESULTS_FOLDER'], session_id)
        pdf_path = os.path.join(results_path, '열일바다청소_보고서.pdf')
        pdf.output(pdf_path)
        return pdf_path
    except Exception as e:
        raise ValueError(f"PDF 보고서 생성 중 오류가 발생했습니다: {str(e)}")

# 라우트 정의
@app.route('/')
def index():
    return render_template('index.html', max_images=app.config['MAX_IMAGES'])

@app.route('/upload', methods=['POST', 'GET'])
def upload_file():
    # GET 요청이 오면 메인 페이지로 리다이렉트
    if request.method == 'GET':
        return redirect(url_for('index'))
    
    # 디버그 로깅 추가
    app.logger.info("Upload request received")
    app.logger.info(f"Files in request: {request.files}")
    
    # POST 요청 처리
    session_id = str(uuid.uuid4())
    results_path = os.path.join(app.config['RESULTS_FOLDER'], session_id)
    images_path = os.path.join(app.config['IMAGES_FOLDER'], session_id)
    os.makedirs(results_path, exist_ok=True)
    os.makedirs(images_path, exist_ok=True)
    
    excel_files_info = [] # (path, original_filename)
    image_files = []
    
    try:
        if 'files' not in request.files: 
            app.logger.error("No files in request")
            return jsonify({'status': 'error', 'message': '파일이 업로드되지 않았습니다.'}), 400
        
        files = request.files.getlist('files')
        app.logger.info(f"Number of files: {len(files)}")
        
        if not files or all(file.filename == '' for file in files): 
            app.logger.error("No files selected")
            return jsonify({'status': 'error', 'message': '파일이 선택되지 않았습니다.'}), 400
        
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_ext = filename.rsplit('.', 1)[1].lower()
                if file_ext in ['xlsx', 'xls']:
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{session_id}_{filename}") # 세션 ID 추가하여 중복 방지
                    file.save(file_path)
                    excel_files_info.append({'path': file_path, 'original_filename': filename})
                    app.logger.info(f"Saved excel file: {file_path}")
                elif file_ext in ['jpg', 'jpeg', 'png']:
                    if len(image_files) < app.config['MAX_IMAGES']:
                        img_path = os.path.join(images_path, filename)
                        file.save(img_path)
                        image_files.append(filename)
                        app.logger.info(f"Saved image file: {img_path}")
        
        if not excel_files_info:
            app.logger.error("No excel files uploaded")
            return jsonify({'status': 'error', 'message': '엑셀 파일이 업로드되지 않았습니다.'}), 400
        
        # 각 엑셀 파일 개별 분석
        all_analysis_results = []
        for idx, file_info in enumerate(excel_files_info):
            try:
                app.logger.info(f"Processing file {idx+1}: {file_info['path']}")
                df = clean_data(file_info['path'])
                df.attrs['original_filename'] = file_info['original_filename'] # 원본 파일명 추가
                analysis_result = analyze_single_data(df, session_id, idx + 1)
                all_analysis_results.append(analysis_result)
                app.logger.info(f"Analysis completed for file {idx+1}")
            except Exception as e:
                app.logger.error(f"Error analyzing file {idx+1}: {str(e)}")
                app.logger.exception("Exception details:")
                return jsonify({'status': 'error', 'message': f"데이터 분석 중 오류가 발생했습니다 (파일 {idx + 1}): {str(e)}"}), 500
            
        # PDF 보고서 생성 (개별 분석 결과 리스트 전달)
        try:
            app.logger.info("Generating PDF report")
            pdf_path = generate_pdf_report(all_analysis_results, session_id, image_files)
            app.logger.info(f"PDF report generated: {pdf_path}")
        except Exception as e:
            app.logger.error(f"Error generating PDF: {str(e)}")
            app.logger.exception("Exception details:")
            return jsonify({'status': 'error', 'message': f"PDF 보고서 생성 중 오류가 발생했습니다: {str(e)}"}), 500
        
        # 세션 정보 저장 (모든 분석 결과 저장)
        session_info = {
            'excel_files': [info['original_filename'] for info in excel_files_info],
            'image_files': image_files,
            'analysis_results': all_analysis_results  # 모든 분석 결과 저장
        }
        with open(os.path.join(results_path, 'session_info.json'), 'w', encoding='utf-8') as f:
            json.dump(session_info, f, ensure_ascii=False, indent=2)
        
        # 리다이렉트 대신 결과 URL을 JSON으로 반환
        results_url = url_for('results', session_id=session_id)
        app.logger.info(f"Returning success with redirect URL: {results_url}")
        return jsonify({'status': 'success', 'redirect_url': results_url}), 200
    
    except Exception as e:
        # 오류 발생 시 생성된 폴더/파일 정리
        app.logger.error(f"Unexpected error: {str(e)}")
        app.logger.exception("Exception details:")
        if os.path.exists(results_path): shutil.rmtree(results_path)
        if os.path.exists(images_path): shutil.rmtree(images_path)
        return jsonify({'status': 'error', 'message': f"예상치 못한 오류가 발생했습니다: {str(e)}"}), 500
    
    except Exception as e:
        # 오류 발생 시 생성된 폴더/파일 정리
        if os.path.exists(results_path): shutil.rmtree(results_path)
        if os.path.exists(images_path): shutil.rmtree(images_path)
        for file_info in excel_files_info:
             if os.path.exists(file_info['path']): os.remove(file_info['path'])
        return render_template('error.html', error=str(e))

@app.route('/results/<session_id>')
def results(session_id):
    results_path = os.path.join(app.config['RESULTS_FOLDER'], session_id)
    images_path = os.path.join(app.config['IMAGES_FOLDER'], session_id)
    try:
        # 세션 정보 로드 (모든 분석 결과)
        with open(os.path.join(results_path, 'session_info.json'), 'r', encoding='utf-8') as f:
            session_info = json.load(f)
            all_analysis_results = session_info.get('analysis_results', [])
            image_files = session_info.get('image_files', [])
            
        if not all_analysis_results:
            raise ValueError("분석 결과를 찾을 수 없습니다.")

        return render_template('results.html', 
                              session_id=session_id, 
                              all_analysis_results=all_analysis_results,
                              image_files=image_files,
                              now=datetime.now())  # now 변수 추가
    except Exception as e:
        return render_template('error.html', error=f"결과 로드 중 오류가 발생했습니다: {str(e)}")

@app.route('/download/<session_id>/<file_type>')
def download_file(session_id, file_type):
    results_path = os.path.join(app.config['RESULTS_FOLDER'], session_id)
    try:
        if file_type == 'pdf':
            return send_from_directory(results_path, '열일바다청소_보고서.pdf', as_attachment=True)
        return redirect(url_for('results', session_id=session_id))
    except Exception as e:
        return render_template('error.html', error=f"파일 다운로드 중 오류가 발생했습니다: {str(e)}")

@app.route('/image/<session_id>/<image_name>')
def get_image(session_id, image_name):
    results_path = os.path.join(app.config['RESULTS_FOLDER'], session_id)
    return send_from_directory(results_path, image_name)

@app.route('/uploaded_image/<session_id>/<image_name>')
def get_uploaded_image(session_id, image_name):
    images_path = os.path.join(app.config['IMAGES_FOLDER'], session_id)
    return send_from_directory(images_path, image_name)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
    os.makedirs(app.config['IMAGES_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)

# AWS WSGI 엔트리 포인트용


