import subprocess
import sys
import os
import json

# --- 終極修正：直接在程式啟動時安裝所有套件 ---
def install_requirements():
    # 這裡列出所有運算需要的套件
    requirements = [
        "yfinance",
        "pandas==1.5.3",
        "pandas-ta",
        "requests",
        "gspread",
        "oauth2client"
    ]
    for package in requirements:
        try:
            # 使用 --no-deps 避免 pandas_ta 的版本衝突
            cmd = [sys.executable, "-m", "pip", "install", package]
            if "pandas-ta" in package:
                cmd.append("--no-deps")
            subprocess.check_call(cmd)
        except Exception as e:
            print(f"安裝 {package} 時跳過或出錯: {e}")

# 執行安裝
install_requirements()

# --- 安裝完成後才載入套件 ---
import yfinance as yf
import pandas_ta as ta
import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 從 GitHub Secrets 讀取設定 ---
TG_TOKEN = "7959417356:AAFosIMtNYPhbr6xr1gvz9bhskkK_MR2OA8"
TG_CHAT_ID = "8398567813"
SHEET_ID = os.getenv("SHEET_ID")
GCP_JSON = os.getenv("GCP_JSON")

def send_tg(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass

def get_portfolio_from_sheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # 確保 GCP_JSON 存在
        if not GCP_JSON:
            print("❌ 錯誤：找不到 GCP_JSON 環境變數")
            return []
        creds_dict = json.loads(GCP_JSON)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).sheet1
        return sheet.get_all_records()
    except Exception as e:
        print(f"❌ 讀取 Sheets 失敗: {e}")
        return []

def monitor():
    portfolio = get_portfolio_from_sheets()
    if not portfolio:
        print("💡 試算表為空或讀取失敗")
        return

    for item in portfolio:
        ticker = str(item.get('Ticker', '')).strip()
        entry_p = item.get('Entry_Price')
        status = item.get('Status')
        
        # 只檢查標記為 Active 的股票
        if not ticker or status != 'Active':
            continue

        try:
            # 抓取股價
            df = yf.download(ticker, period='1y', progress=False)
            if df.empty:
                continue
            
            # 修正多重索引問題
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            
            # 計算指標：SAR 與 3日最低點
            df['Low3'] = df['Low'].rolling(window=3).min()
            sar_df = ta.psar(df['High'], df['Low'], df['Close'])
            df['SAR'] = sar_df[sar_df.columns[0]].fillna(sar_df[sar_df.columns[1]])
            
            curr = df.iloc[-1]
            cur_p = curr['Close']
            entry_p = float(entry_p)
            diff_pct = ((cur_p - entry_p) / entry_p) * 100
            
            # --- 判斷邏輯 ---
            # 1. 獲利且跌破三日低點
            if diff_pct > 0 and cur_p < curr['Low3']:
                send_tg(f"⚠️ *動能警告*：{ticker}\n現價 `{cur_p:.2f}` 跌破三日低點 `{curr['Low3']:.2f}`！\n目前獲利：`{diff_pct:.1f}%`")
            
            # 2. 獲利達 10% 以上
            elif diff_pct >= 10.0:
                send_tg(f"💰 *獲利達標*：{ticker}\n已達成目標 `{diff_pct:.1f}%`！\n現價：`{cur_p:.2f}`")
            
            # 3. 觸發拋物線停損 (SAR)
            elif cur_p < curr['SAR']:
                send_tg(f"🚨 *觸發停損*：{ticker}\n跌破 SAR 支撐 `{curr['SAR']:.2f}`！\n請考慮離場。")
                
        except Exception as e:
            print(f"處理 {ticker} 時出錯: {e}")

if __name__ == "__main__":
    monitor()
