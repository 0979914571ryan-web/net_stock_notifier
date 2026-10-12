from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import sqlite3
from datetime import datetime

# 🌟 完美整合：匯入你自己寫的核心引擎邏輯！
from core_engine import init_test_db, insert_trade_record, calculate_portfolio

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

LINE_CHANNEL_ACCESS_TOKEN = "jrsZWzhulJrsq2OdM9sXUNPXnV7YcirbfbygsmL80HBjJZfJO4gvqtmPi+zy1nn7cIRb6D4wo5mimTtZAa9VHai/XRbRF3BBztdjfZTKuQe8HNYMcsQTSA2rsdYFowyiHZ4D5WjXCNYhF2XeaVzvBwdB04t89/1O/w1cDnyilFU="
MY_USER_ID = "Ue1a6a9a47fcc84f36ad502d62f20806d"

init_test_db() # 啟動時自動檢查並建立 portfolio_new.db

def send_line_push_message(user_id: str, message_text: str):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    requests.post(url, headers=headers, json={"to": user_id, "messages": [{"type": "text", "text": message_text}]})

def get_portfolio_msg(user_id):
    conn = sqlite3.connect("portfolio_new.db")
    summary, details = calculate_portfolio(conn, user_id)
    conn.close()
    
    if not details: return "目前資料庫中沒有任何交易紀錄。"
    
    msg = "📊 【專業資產與損益戰報】\n"
    msg += f"💰 總資產：{summary['總資產']:,.0f}\n"
    msg += f"💵 淨資產：{summary['淨資產']:,.0f}\n"
    msg += f"📉 總負債：{summary['負債']:,.0f} (含利息稅費)\n"
    msg += "--------------------\n"
    for d in details:
        msg += f"• {d['代號']} ({d['類型']}) | {d['股數']}股\n  現價: {d['現價']:.1f} | 淨值: {d['淨值']:,.0f}\n"
    return msg

@app.get("/liff", response_class=HTMLResponse)
async def liff_page():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

async def handle_transaction_logic(request: Request):
    try:
        data = await request.json()
        stock_id = data.get("stock_id")
        shares = int(data.get("shares", 0))
        price = float(data.get("price", 0))
        trade_type = data.get("type", "現股") # 接收前端的現股/融資
        trade_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))

        # 🌟 寫入你的 portfolio_new.db
        conn = sqlite3.connect("portfolio_new.db")
        insert_trade_record(conn, MY_USER_ID, trade_date, trade_type, stock_id, shares, price)
        conn.close()

        msg = "📢 【交易變更通知】新增成功！\n\n" + get_portfolio_msg(MY_USER_ID)
        send_line_push_message(MY_USER_ID, msg)
        return {"status": "success"}
    except Exception as e:
        print("Error:", e)
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/add_transaction")
async def api_add(request: Request): return await handle_transaction_logic(request)

@app.post("/webhook")
async def line_webhook(request: Request):
    body = await request.json()
    for event in body.get("events", []):
        if event.get("type") == "message" and event["message"].get("type") == "text":
            if event["message"].get("text").strip() == "更新":
                send_line_push_message(event["source"].get("userId"), get_portfolio_msg(MY_USER_ID))
    return JSONResponse(content={"status": "ok"})

scheduler = BackgroundScheduler()
def scheduled_job():
    send_line_push_message(MY_USER_ID, "⏰ 【每日收盤戰報】\n\n" + get_portfolio_msg(MY_USER_ID))
scheduler.add_job(scheduled_job, 'cron', hour=15, minute=0)
scheduler.start()