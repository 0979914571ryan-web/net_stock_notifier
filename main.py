import sqlite3
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf

app = FastAPI()

# 掛載靜態檔案資料夾 (存放 index.html)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==================== 設定區 ====================
LINE_CHANNEL_ACCESS_TOKEN = "jrsZWzhulJrsq2OdM9sXUNPXnV7YcirbfbygsmL80HBjJZfJO4gvqtmPi+zy1nn7cIRb6D4wo5mimTtZAa9VHai/XRbRF3BBztdjfZTKuQe8HNYMcsQTSA2rsdYFowyiHZ4D5WjXCNYhF2XeaVzvBwdB04t89/1O/w1cDnyilFU="
MY_USER_ID = "Ue1a6a9a47fcc84f36ad502d62f20806d"
# ================================================

# 初始化 SQLite 資料庫
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT,
            shares REAL,
            price REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# 發送 LINE 主動推播訊息的核心函式
def send_line_push_message(user_id: str, message_text: str):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    data = {
        "to": user_id,
        "messages": [{"type": "text", "text": message_text}]
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()

# 計算資產與損益的輔助函式
def get_asset_summary_text():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT stock_id, shares, price FROM transactions")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "目前資料庫中沒有任何交易紀錄。"

    msg = "📊 【即時資產與損益戰報】\n"
    total_cost = 0
    total_market_value = 0

    for stock_id, shares, buy_price in rows:
        # 處理台股代號格式給 yfinance 抓取 (例如 2327 -> 2327.TW)
        ticker_symbol = f"{stock_id}.TW" if not stock_id.endswith(('.TW', '.TWO')) else stock_id
        try:
            ticker = yf.Ticker(ticker_symbol)
            # 取得最新收盤價
            todays_data = ticker.history(period="1d")
            current_price = todays_data['Close'].iloc[-1] if not todays_data.empty else buy_price
        except Exception:
            current_price = buy_price

        cost = shares * buy_price
        market_value = shares * current_price
        pnl = market_value - cost
        pnl_pct = (pnl / cost) * 100 if cost > 0 else 0

        total_cost += cost
        total_market_value += market_value

        msg += f"\n• 股票：{stock_id}\n  持股：{shares} 股 | 成本：{buy_price:.1f}\n  現價：{current_price:.1f} | 損益：{pnl:+.1f} ({pnl_pct:+.2f}%)\n"

    total_pnl = total_market_value - total_cost
    total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost > 0 else 0
    msg += f"\n--------------------\n💰 總成本：{total_cost:,.1f}\n📈 總市值：{total_market_value:,.1f}\n🔥 總損益：{total_pnl:+,.1f} ({total_pnl_pct:+.2f}%)"
    return msg

# 1. LIFF 網頁前端入口
@app.get("/liff", response_class=HTMLResponse)
async def liff_page():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

# 2. 接收前端表單送出（新增/修改交易）並立即推播
@app.post("/api/add_transaction")
async def add_transaction(request: Request):
    data = await request.json()
    stock_id = data.get("stock_id")
    shares = float(data.get("shares", 0))
    price = float(data.get("price", 0))

    # 寫入 SQLite 資料庫
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO transactions (stock_id, shares, price) VALUES (?, ?, ?)", (stock_id, shares, price))
    conn.commit()
    conn.close()

    # 立即發送變更通知與最新資產狀況
    summary = get_asset_summary_text()
    push_msg = f"📢 【交易變更通知】已成功新增/更新！\n\n{summary}"
    send_line_push_message(MY_USER_ID, push_msg)

    return {"status": "success", "message": "Transaction added and pushed."}

# 3. LINE Webhook 接收聊天室訊息（當用戶輸入 "更新" 時觸發）
@app.post("/webhook")
async def line_webhook(request: Request):
    body = await request.json()
    events = body.get("events", [])
    
    for event in events:
        if event.get("type") == "message" and event["message"].get("type") == "text":
            user_text = event["message"].get("text").strip()
            user_id = event["source"].get("userId")
            
            # 如果使用者輸入「更新」
            if user_text == "更新":
                summary = get_asset_summary_text()
                send_line_push_message(user_id, summary)
                
    return JSONResponse(content={"status": "ok"})

# 4. 設定每日下午 3:00 自動推播排程
scheduler = BackgroundScheduler()
def scheduled_job():
    if MY_USER_ID and "請把" not in MY_USER_ID:
        summary = get_asset_summary_text()
        push_msg = f"⏰ 【每日收盤戰報】下午 3:00 自動結算：\n\n{summary}"
        send_line_push_message(MY_USER_ID, push_msg)

# 每天 15:00 執行
scheduler.add_job(scheduled_job, 'cron', hour=15, minute=0)
scheduler.start()

@app.get("/")
async def root():
    return {"status": "Running", "message": "Go to /liff for frontend"}