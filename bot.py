import os
import pandas_ta as ta
import yfinance as yf
import pandas as pd
import numpy as np
import logging
import time
import re
import requests
import random
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ==========================================
# ⚙️ 核心設定區
# ==========================================
BOT_TOKEN = "7959417356:AAFosIMtNYPhbr6xr1gvz9bhskkK_MR2OA8"
CHAT_ID = "8398567813"

# 預設金名單
best_performance_stocks = ['NVDA', 'TSM', 'AMD', 'AAPL', '2330.TW', '3017.TW']

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

# ==========================================
# 🛡️ 深度偽裝數據抓取邏輯
# ==========================================
def fetch_data_with_retry(ticker):
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    ]
    
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': random.choice(user_agents)})
        
        # 嘗試第一種方式: yfinance
        stock = yf.Ticker(ticker, session=session)
        df = stock.history(period="6mo", interval="1d", timeout=20)
        
        if df.empty or len(df) < 20:
            # 嘗試第二種方式: 強制重新下載
            df = yf.download(ticker, period="6mo", progress=False, auto_adjust=True, threads=False, session=session)
        
        if df.empty: return "IP_BLOCKED"
        
        # 格式化欄位名
        df.columns = [str(c).capitalize() for c in df.columns]
        
        # 指標計算 (修正 ffill)
        df['SAR'] = ta.psar(df['High'], df['Low'], df['Close'])['PSARl_0.02_0.2'].ffill()
        df['MA20'] = ta.sma(df['Close'], length=20)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=22)
        df['CE'] = df['Close'] - (df['ATR'] * 3.0)
        
        return df.dropna()
    except Exception as e:
        return f"ERR:{str(e)[:15]}"

# ==========================================
# 🤖 Telegram 功能指令
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != CHAT_ID: return
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton("📡 深度連線測試", callback_data='test')],
                [InlineKeyboardButton("🔍 即時診斷名單", callback_data='m1')],
                [InlineKeyboardButton("📊 交易計畫/持倉", callback_data='m3')]]
    await update.message.reply_text("✅ **V10.0 終極修復版**\n已更新請求標頭與重試邏輯，請點選測試：", 
                                   reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    
    if query.data == 'test':
        await query.message.reply_text("🧪 正在嘗試繞過防火牆...")
        res = fetch_data_with_retry('NVDA')
        if isinstance(res, pd.DataFrame):
            await query.message.reply_text(f"🔥 **成功繞過！**\nNVDA 現價: `{res['Close'].iloc[-1]:.2f}`", parse_mode='Markdown')
        else:
            await query.message.reply_text(f"❌ 依然失敗: `{res}`\n這代表 PythonAnywhere 的 IP 已完全死亡，請看下方說明。")

    elif query.data == 'm1':
        await query.message.reply_text("🔎 正在檢索全球數據...")
        report = "📊 **診斷報告**\n"
        for t in best_performance_stocks:
            df = fetch_data_with_retry(t)
            if isinstance(df, pd.DataFrame):
                c = df.iloc[-1]
                p, r, m, s = float(c['Close']), float(c['RSI']), float(c['MA20']), float(c['SAR'])
                icon = "✅" if (p > m and p > s and 50 < r < 70) else "❌"
                report += f"{icon} `{t}`: 價{p:.1f} | RSI:{r:.1f}\n"
            else:
                report += f"⚠️ `{t}`: 連線失敗\n"
        await query.message.reply_text(report, parse_mode='Markdown')

    elif query.data == 'm3':
        await query.message.reply_text("📝 請輸入股票代碼 (例: `AMD`)：")
        context.user_data['state'] = 'WAIT_TICKER'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != CHAT_ID: return
    state = context.user_data.get('state')
    text = update.message.text.upper().strip()

    if state == 'WAIT_TICKER':
        ticker = text + ".TW" if (text.isdigit() and len(text) <= 4) else text
        context.user_data['temp_ticker'] = ticker
        await update.message.reply_text(f"✅ 已選定 `{ticker}`\n💰 請輸入您的 **買入成本**：")
        context.user_data['state'] = 'WAIT_COST'

    elif state == 'WAIT_COST':
        try:
            cost = float(re.search(r"(\d+\.?\d*)", text).group(1))
            ticker = context.user_data.get('temp_ticker')
            df = fetch_data_with_retry(ticker)
            if isinstance(df, pd.DataFrame):
                c = df.iloc[-1]
                p, s, ce = float(c['Close']), float(c['SAR']), float(c['CE'])
                pnl = (p - cost) / cost * 100
                exit_p = max(s, ce)
                msg = (f"🛡️ **{ticker} 持倉監控**\n---\n"
                       f"💰 成本: `{cost:.2f}` | 損益: `{pnl:+.2f}%`\n"
                       f"💹 現價: `{p:.2f}`\n🚨 停損線: `{exit_p:.2f}`\n"
                       f"📝 狀態: {'⚠️ 趨勢走弱' if p < exit_p else '✅ 持有安全'}")
                await update.message.reply_text(msg, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ 數據獲取受阻: {df}")
            context.user_data['state'] = None
        except:
            await update.message.reply_text("⚠️ 請輸入數字。")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()