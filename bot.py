import yfinance as yf
import pandas_ta as ta
import requests
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

# --- 從 GitHub Secrets 讀取設定 ---
TG_TOKEN = "7959417356:AAFosIMtNYPhbr6xr1gvz9bhskkK_MR2OA8"
TG_CHAT_ID = "8398567813"
SHEET_ID = os.getenv("SHEET_ID")
GCP_JSON = os.getenv("GCP_JSON")

def send_tg(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=payload, timeout=10)

def get_portfolio_from_sheets():
    """連動您的 Stock_Monitor 試算表"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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
    for item in portfolio:
        ticker = str(item.get('Ticker', '')).strip()
        entry_p = item.get('Entry_Price')
        status = item.get('Status')

        if not ticker or status != 'Active': continue

        try:
            df = yf.download(ticker, period='1y', progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            
            # 計算防禦指標
            df['Low3'] = df['Low'].rolling(window=3).min()
            sar_df = ta.psar(df['High'], df['Low'], df['Close'])
            df['SAR'] = sar_df[sar_df.columns[0]].fillna(sar_df[sar_df.columns[1]])
            
            curr = df.iloc[-1]
            cur_p = curr['Close']
            diff_pct = ((cur_p - entry_p) / entry_p) * 100
            
            # 智慧通知邏輯
            if diff_pct > 0 and cur_p < curr['Low3']:
                send_tg(f"⚠️ *動能警告*：{ticker} 破三日低點！獲利剩 `{diff_pct:.1f}%`。")
            elif diff_pct >= 10.0:
                send_tg(f"💰 *獲利達標*：{ticker} 已賺 `{diff_pct:.1f}%`！")
            elif cur_p < curr['SAR']:
                send_tg(f"🚨 *觸發停損*：{ticker} 跌破 SAR `{curr['SAR']:.2f}`！")
        except: continue

if __name__ == "__main__":
    monitor()
