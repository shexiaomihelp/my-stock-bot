import os
import json
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 參數設定 ---
TG_TOKEN = "7959417356:AAFosIMtNYPhbr6xr1gvz9bhskkK_MR2OA8"
TG_CHAT_ID = "8398567813"
SHEET_ID = os.getenv("SHEET_ID")
GCP_JSON_STR = os.getenv("GCP_JSON")

STOCKS_TO_WATCH = ['2330.TW', '2317.TW', '2454.TW', 'NVDA', 'TSLA', 'PLTR', 'RKLB']

def send_tg(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=15)
    except:
        pass

def run_scan():
    target_list = STOCKS_TO_WATCH
    try:
        if GCP_JSON_STR and SHEET_ID:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds_dict = json.loads(GCP_JSON_STR)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            portfolio = client.open_by_key(SHEET_ID).sheet1.get_all_records()
            target_list = [item.get('Ticker') for item in portfolio if item.get('Ticker')]
    except:
        print("Sheets 讀取失敗，使用預設標的")

    signals = []
    for t in target_list:
        try:
            df = yf.download(t, period='1y', progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            
            df['EMA20'] = ta.ema(df['Close'], length=20)
            df['RSI'] = ta.rsi(df['Close'], length=14)
            sar_df = ta.psar(df['High'], df['Low'], df['Close'])
            df['SAR'] = sar_df[sar_df.columns[0]].fillna(sar_df[sar_df.columns[1]])
            
            curr = df.iloc[-1]
            if curr['Close'] > curr['EMA20'] and curr['RSI'] > 50 and curr['Close'] > curr['SAR']:
                signals.append(f"🎯 *{t}* 觸發多頭訊號")
        except:
            continue

    report = "📊 *V11.0 雲端正式版*\n" + ("\n".join(signals) if signals else "⚠️ 目前無符合標的")
    send_tg(report)

if __name__ == "__main__":
    run_scan()
