import os
import subprocess
import sys

# --- 0. 自動安裝缺失套件 (解決 GitHub 環境報錯) ---
def install_requirements():
    packages = ['yfinance', 'pandas==1.5.3', 'pandas_ta', 'requests']
    for p in packages:
        try:
            # 使用 --no-deps 安裝 pandas_ta 以避開版本衝突
            cmd = [sys.executable, "-m", "pip", "install", p]
            if p == 'pandas_ta': cmd.append("--no-deps")
            subprocess.check_call(cmd)
        except:
            pass

install_requirements()

import pandas as pd
import yfinance as yf
import pandas_ta as ta
import requests

# --- 1. 從 GitHub Secrets 讀取設定 ---
# 請確保您在 GitHub Settings > Secrets 裡有 SHEET_ID, GCP_JSON
# 若您這版不需要讀取 Google Sheet，可直接保留以下 TG 設定
TELEGRAM_BOT_TOKEN = "7959417356:AAFosIMtNYPhbr6xr1gvz9bhskkK_MR2OA8"
TELEGRAM_CHAT_ID = "8398567813"

# 2026 戰略標的
STOCKS_TO_WATCH = [
    '2330.TW', '2317.TW', '2454.TW', '3017.TW', '6669.TW',
    'NVDA', 'AVGO', 'ASML', 'ARM', 'MSFT', 'AMZN',
    'ISRG', 'RKLB', 'PLTR', 'TSLA'
]

MA_PERIOD = 20
VOL_THRESHOLD = 1.1

# --- 2. 核心運算 ---
def get_data(ticker):
    try:
        df = yf.download(ticker, period='1y', progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
        
        df['EMA20'] = ta.ema(df['Close'], length=MA_PERIOD)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        df['V_MA5'] = ta.sma(df['Volume'], length=5)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        sar_df = ta.psar(df['High'], df['Low'], df['Close'])
        df['SAR'] = sar_df[sar_df.columns[0]].fillna(sar_df[sar_df.columns[1]])
        
        return df.dropna()
    except: return None

def send_tg(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=payload, timeout=15)

def run_scan():
    signals, overheated, low_vol = [], [], []

    for t in STOCKS_TO_WATCH:
        df = get_data(t)
        if df is None: continue
        curr = df.iloc[-1]
        
        p, ema, atr = curr['Close'], curr['EMA20'], curr['ATR']
        vol, v_ma5 = curr['Volume'], curr['V_MA5']
        
        # ATR 動態乖離計算
        dev_price = p - ema
        max_allowed_dev = atr * 2.0 
        
        if p > ema and curr['RSI'] > 50 and p > curr['SAR']:
            if vol < v_ma5 * VOL_THRESHOLD:
                low_vol.append(t)
                continue
            
            if dev_price > max_allowed_dev:
                overheated.append(f"🔥 `{t}`")
            else:
                risk = p - curr['SAR']
                tp = p + (risk * 1.5)
                signals.append(f"🎯 *{t}*\n├ 現價: `{p:.2f}`\n├ 🛡️ 停損: `{curr['SAR']:.2f}`\n└ 🚀 停利: `{tp:.2f}`")

    # 報告整合
    report = "📊 *V11.0 2026 戰略掃描*\n" + "━"*15 + "\n"
    report += "✅ *量價齊揚：*\n" + ("\n\n".join(signals) if signals else "⚠️ 目前無標的符合條件")
    
    if overheated:
        report += "\n\n過熱標的 (不宜追高)：\n`" + ", ".join(overheated) + "`"
    if low_vol:
        report += "\n\n量能不足：\n`" + ", ".join(low_vol) + "`"
    
    send_tg(report)

if __name__ == "__main__":
    while True:
        try:
            run_scan()
            print("🕒 掃描完成，1 小時後將再次執行...")
            time.sleep(3600)  # 暫停 3600 秒 (1 小時)
        except KeyboardInterrupt:
            print("停止自動化掃描")
            break
        except Exception as e:
            print(f"自動化過程發生錯誤: {e}")
            time.sleep(60) # 發生錯誤時等 1 分鐘再試
