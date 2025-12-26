import os
import subprocess
import sys
import json
import time

# ==========================================
# 0. 環境自動修復 (解決雲端套件缺失與版本衝突)
# ==========================================
def cloud_fix():
    print("⏳ 正在初始化環境並安裝套件...")
    # 這裡使用您指定的 6 個套件清單
    pkgs = ["yfinance", "pandas==1.5.3", "requests", "gspread", "oauth2client"]
    for p in pkgs:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", p, "--quiet"])
        except:
            pass
    # 強制安裝 pandas-ta (必須用橫線，且不檢查相依性以防報錯)
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas-ta", "--no-deps", "--quiet"])
    except:
        pass
    print("✅ 環境準備就緒")

# 啟動修復程序
cloud_fix()

# ==========================================
# 1. 導入套件 (安裝後才執行)
# ==========================================
import pandas as pd
import yfinance as yf
import pandas_ta as ta  # 導入時使用底線
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 2. 參數設定 (請確保 GitHub Secrets 已設定)
# ==========================================
TG_TOKEN = "7959417356:AAFosIMtNYPhbr6xr1gvz9bhskkK_MR2OA8"
TG_CHAT_ID = "8398567813"
SHEET_ID = os.getenv("SHEET_ID")
GCP_JSON_STR = os.getenv("GCP_JSON")

# 2026 戰略標的 (備用名單)
STOCKS_TO_WATCH = [
    '2330.TW', '2317.TW', '2454.TW', '3017.TW', '6669.TW',
    'NVDA', 'AVGO', 'ASML', 'ARM', 'MSFT', 'AMZN',
    'ISRG', 'RKLB', 'PLTR', 'TSLA'
]

# ==========================================
# 3. 核心功能
# ==========================================
def send_tg(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=15)
    except:
        pass

def get_portfolio():
    # 優先嘗試讀取 Google Sheets
    try:
        if not GCP_JSON_STR or not SHEET_ID:
            return None
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(GCP_JSON_STR)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_ID).sheet1.get_all_records()
    except Exception as e:
        print(f"Sheets 讀取失敗，改用預設清單: {e}")
        return None

def run_scan():
    portfolio = get_portfolio()
    # 如果 Sheets 讀取失敗，使用內建戰略名單
    target_list = [item.get('Ticker') for item in portfolio if item.get('Ticker')] if portfolio else STOCKS_TO_WATCH
    
    signals, overheated, low_vol = [], [], []

    for t in target_list:
        try:
            df = yf.download(t, period='1y', progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            
            # 指標計算
            df['EMA20'] = ta.ema(df['Close'], length=20)
            df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
            df['V_MA5'] = ta.sma(df['Volume'], length=5)
            df['RSI'] = ta.rsi(df['Close'], length=14)
            sar_df = ta.psar(df['High'], df['Low'], df['Close'])
            df['SAR'] = sar_df[sar_df.columns[0]].fillna(sar_df[sar_df.columns[1]])
            
            curr = df.iloc[-1]
            p, ema, atr, vol, v_ma5 = curr['Close'], curr['EMA20'], curr['ATR'], curr['Volume'], curr['V_MA5']
            
            # ATR 動態乖離過濾
            if p > ema and curr['RSI'] > 50 and p > curr['SAR']:
                if vol < v_ma5 * 1.1:
                    low_vol.append(t)
                elif (p - ema) > (atr * 2.0):
                    overheated.append(f"🔥 `{t}`")
                else:
                    risk = p - curr['SAR']
                    tp = p + (risk * 1.5)
                    signals.append(f"🎯 *{t}*\n├ 現價: `{p:.2f}`\n├ 🛡️ 停損: `{curr['SAR']:.2f}`\n└ 🚀 停利: `{tp:.2f}`")
        except:
            continue

    # 報告整合
    report = "📊 *V11.0 雲端掃描報告*\n" + "━"*15 + "\n"
    report += "✅ *量價齊揚：*\n" + ("\n\n".join(signals) if signals else "⚠️ 目前無符合標的")
    if overheated: report += "\n\n過熱標的：\n`" + ", ".join(overheated) + "`"
    if low_vol: report += "\n\n量能不足：\n`" + ", ".join(low_vol) + "`"
    
    send_tg(report)

if __name__ == "__main__":
    run_scan()
