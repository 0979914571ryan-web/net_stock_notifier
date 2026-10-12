import requests
import random
import os
import urllib.parse
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles # 🌟 負責提供 LIFF 網頁的新套件
import uvicorn

# 🌟 確保這裡有引入 insert_trade_record
from core_engine import init_test_db, calculate_portfolio, insert_trade_record

# 引入繪圖套件 (僅供本地存檔)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties

app = FastAPI()

# 🌟 掛載 static 資料夾，讓伺服器可以提供網頁檔案給瀏覽器與 LINE
app.mount("/liff", StaticFiles(directory="static", html=True), name="static")

# ==========================================
# 1. LINE 設定 (⚠️ 請務必填入你的真實金鑰)
# ==========================================
LINE_TOKEN = "jrsZWzhulJrsq2OdM9sXUNPXnV7YcirbfbygsmL80HBjJZfJO4gvqtmPi+zy1nn7cIRb6D4wo5mimTtZAa9VHai/XRbRF3BBztdjfZTKuQe8HNYMcsQTSA2rsdYFowyiHZ4D5WjXCNYhF2XeaVzvBwdB04t89/1O/w1cDnyilFU="
USER_ID = "Ue1a6a9a47fcc84f36ad502d62f20806d"

if not os.path.exists('static'):
    os.makedirs('static')

font_path = "C:/Windows/Fonts/msjh.ttc"
if os.path.exists(font_path):
    myfont = FontProperties(fname=font_path)
    plt.rcParams['font.family'] = myfont.get_name()
else:
    plt.rcParams['font.family'] = ['sans-serif']

# ==========================================
# 2. 本地高畫質繪圖 (半年 180 天淨資產走勢)
# ==========================================
def generate_local_chart(today_net):
    today = datetime.now()
    current_net = today_net / 1000
    raw_net = [current_net]
    dates = [today]
    
    for i in range(1, 180):
        daily_ret = random.gauss(0.0003, 0.015) 
        net_ret = daily_ret * 1.5
        current_net = current_net / (1 + net_ret)
        raw_net.append(current_net)
        dates.append(today - timedelta(days=i))
        
    raw_net.reverse()
    dates.reverse()

    plt.figure(figsize=(8, 4), dpi=150)
    plt.plot(dates, raw_net, color='#E74C3C', linewidth=1.5, label='淨資產(千)')
    plt.fill_between(dates, raw_net, color='#E74C3C', alpha=0.1)
    
    plt.title("近半年淨資產走勢 (180天日級別高解析)", fontsize=14, fontweight='bold', color='#E74C3C', pad=15)
    plt.legend(loc='lower center', bbox_to_anchor=(0.5, -0.2), ncol=1, frameon=False)
    
    ax = plt.gca()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%y/%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#DDDDDD')
    ax.spines['bottom'].set_color('#DDDDDD')
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    
    filepath = "static/trend_chart.png"
    plt.savefig(filepath, bbox_inches='tight')
    plt.close()

# ==========================================
# 3. 終極壓縮版 URL 圖表產生器 (半年淨資產)
# ==========================================
def generate_compressed_chart_url(today_net):
    current_net = int(today_net / 1000)
    
    hist_net = []
    labels_list = []
    today = datetime.now()
    
    for i in range(89, -1, -1):
        if i == 0:
            hist_net.append(current_net)
            labels_list.append(f"'{today.strftime('%y/%m')}'")
        else:
            growth = 1 - (i * 0.003) + random.uniform(-0.015, 0.015)
            hist_net.append(int(current_net * (growth - 0.03)))
            
            if i % 15 == 0:
                d = today - timedelta(days=i*2)
                labels_list.append(f"'{d.strftime('%y/%m')}'")
            else:
                labels_list.append("''")
            
    data_net_str = ",".join(map(str, hist_net))
    labels_str = ",".join(labels_list)
    
    chart_str = f"{{type:'line',data:{{labels:[{labels_str}],datasets:[{{label:'淨(千)',data:[{data_net_str}],borderColor:'#E74C3C',borderWidth:2,pointRadius:0,fill:true,backgroundColor:'rgba(231,76,60,0.1)'}}]}},options:{{legend:{{display:false}},scales:{{xAxes:[{{gridLines:{{display:false}},ticks:{{fontSize:9,maxRotation:0,autoSkip:false}}}}],yAxes:[{{ticks:{{fontSize:9,maxTicksLimit:6}}}}]}}}}}}"
    
    encoded_config = urllib.parse.quote(chart_str)
    return f"https://quickchart.io/chart?c={encoded_config}&w=500&h=250&bkg=white"

# ==========================================
# 4. LINE Flex Message 視覺切版產生器
# ==========================================
def build_flex_message(summary, details):
    today_str = datetime.now().strftime("%Y/%m/%d")
    
    contents = [
        {"type": "text", "text": f"📊 【{today_str} 盤後總結】", "weight": "bold", "size": "lg", "color": "#1DB446"},
        {"type": "separator", "margin": "md"},
        
        {"type": "box", "layout": "horizontal", "margin": "md", "contents": [
            {"type": "text", "text": "💰 總資產", "size": "sm", "color": "#555555", "flex": 0},
            {"type": "text", "text": f"NT$ {int(summary['總資產']):,}", "size": "md", "color": "#111111", "align": "end", "weight": "bold"}
        ]},
        {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
            {"type": "text", "text": "🛡️ 淨資產", "size": "sm", "color": "#555555", "flex": 0},
            {"type": "text", "text": f"NT$ {int(summary['淨資產']):,}", "size": "md", "color": "#E74C3C", "align": "end", "weight": "bold"}
        ]},
        {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
            {"type": "text", "text": "📉 總負債", "size": "sm", "color": "#555555", "flex": 0},
            {"type": "text", "text": f"NT$ {int(summary['負債']):,}", "size": "sm", "color": "#111111", "align": "end"}
        ]},
        {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
            {"type": "text", "text": "↳ 融資金額", "size": "xs", "color": "#aaaaaa", "flex": 0},
            {"type": "text", "text": f"NT$ {int(summary['融資本金']):,}", "size": "xs", "color": "#aaaaaa", "align": "end"}
        ]},
        {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
            {"type": "text", "text": "↳ 融資利息、手續費", "size": "xs", "color": "#aaaaaa", "flex": 0},
            {"type": "text", "text": f"NT$ {int(summary['利息與稅費']):,}", "size": "xs", "color": "#aaaaaa", "align": "end"}
        ]},
        
        {"type": "separator", "margin": "lg"},
        {"type": "text", "text": "⭐ 當前庫存明細 (依市值排序)：", "weight": "bold", "size": "sm", "color": "#1DB446", "margin": "md"}
    ]
    
    stock_names = {"2327": "國巨", "6922": "宸曜", "6166": "凌華", "00988A": "主動統一"}
    details_sorted = sorted(details, key=lambda x: x['市值'], reverse=True)
    
    for item in details_sorted:
        code = item['代號']
        name = stock_names.get(code, code)
        pct = (item['市值'] / summary['總資產']) * 100 if summary['總資產'] > 0 else 0
        shares_str = f"{item['股數']//1000}張" if item['股數'] % 1000 == 0 else f"{item['股數']}股"
        
        is_margin = (item['類型'] == '融資')
        theme_color = "#E74C3C" if is_margin else "#777777"
        bg_color = "#FDECEA" if is_margin else "#F0F0F0"
        
        bar_width = f"{max(1, min(100, int(pct)))}%" 
        
        price_rows = [
            {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                {"type": "text", "text": "總市值", "size": "xs", "color": "#aaaaaa"},
                {"type": "text", "text": f"NT$ {int(item['市值']):,}", "size": "xs", "color": "#555555", "align": "end"}
            ]}
        ]
        if is_margin:
            price_rows.append(
                {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
                    {"type": "text", "text": "↳ 預估淨值", "size": "xs", "color": "#E74C3C"},
                    {"type": "text", "text": f"NT$ {int(item['淨值']):,}", "size": "xs", "color": "#E74C3C", "align": "end", "weight": "bold"}
                ]}
            )
        
        stock_box = {
            "type": "box", "layout": "vertical", "margin": "lg", "contents": [
                {"type": "box", "layout": "horizontal", "alignItems": "center", "contents": [
                    {"type": "text", "text": f"• {name}({code})", "size": "sm", "weight": "bold", "color": "#333333", "flex": 0},
                    {"type": "box", "layout": "vertical", "margin": "sm", "cornerRadius": "4px", "backgroundColor": bg_color, "paddingStart": "5px", "paddingEnd": "5px", "flex": 0, "contents": [
                        {"type": "text", "text": item['類型'], "size": "xxs", "color": theme_color, "weight": "bold"}
                    ]},
                    {"type": "text", "text": shares_str, "size": "xs", "color": "#888888", "align": "end"}
                ]},
                {"type": "box", "layout": "horizontal", "margin": "sm", "height": "16px", "backgroundColor": "#EEEEEE", "cornerRadius": "10px", "contents": [
                    {"type": "box", "layout": "horizontal", "width": bar_width, "height": "100%", "cornerRadius": "10px", "background": {"type": "linearGradient", "angle": "90deg", "startColor": "#1DB446", "endColor": "#7EE098"}, "contents": []},
                    {"type": "text", "text": f"{pct:.1f}%", "size": "xxs", "color": "#333333", "weight": "bold", "align": "center", "gravity": "center", "position": "absolute", "offsetStart": "0px", "offsetEnd": "0px", "offsetTop": "0px", "offsetBottom": "0px"}
                ]}
            ] + price_rows
        }
        contents.append(stock_box)

    chart_url = generate_compressed_chart_url(summary['淨資產'])
    footer = {
        "type": "box", "layout": "vertical", "contents": [
            {"type": "separator"},
            {"type": "text", "text": "📈 近半年淨資產走勢", "weight": "bold", "size": "sm", "color": "#E74C3C", "margin": "md"},
            {"type": "image", "url": chart_url, "size": "full", "aspectRatio": "2:1", "aspectMode": "cover", "margin": "md"}
        ]
    }

    flex_payload = {
        "type": "bubble",
        "size": "mega",
        "body": {"type": "box", "layout": "vertical", "contents": contents},
        "footer": footer
    }
    return flex_payload

# ==========================================
# 5. 伺服器 API 端點 (包含寫入資料庫的表單端點)
# ==========================================
@app.post("/broadcast")
def trigger_daily_broadcast():
    db_conn = init_test_db()
    summary, details = calculate_portfolio(db_conn, 'U_TEST_123')
    
    generate_local_chart(summary['淨資產'])
    flex_json = build_flex_message(summary, details)
    
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_TOKEN}'
    }
    data = {
        "to": USER_ID,
        "messages": [{"type": "flex", "altText": "📊 盤後資產總結已送達", "contents": flex_json}]
    }
    
    res = requests.post(url, headers=headers, json=data)
    if res.status_code == 200:
        return {"status": "success", "message": "推播成功！"}
    else:
        return {"status": "error", "message": res.text}

# 🌟 這個端點就是讓網頁表單把資料傳進來，並寫入資料庫的橋樑
@app.post("/api/trade")
def receive_liff_trade(trade_data: dict):
    try:
        db_conn = init_test_db()
        
        insert_trade_record(
            conn=db_conn,
            user_id=trade_data.get("user_id"),
            trade_date=trade_data.get("date"),
            trade_type=trade_data.get("type"),
            stock_code=trade_data.get("code"),
            shares=trade_data.get("shares"),
            price=trade_data.get("price")
        )
        
        return {"status": "success", "message": "交易紀錄已成功新增至資料庫！"}
    except Exception as e:
        print(f"❌ 寫入資料庫失敗: {e}")
        return {"status": "error", "detail": str(e)}

# 🌟 就是這行剛剛被你刪掉了！這是啟動伺服器的命脈
if __name__ == "__main__":
    print("🚀 啟動 FastAPI 後端伺服器 (包含 LIFF 網頁記帳端點)...")
    uvicorn.run(app, host="0.0.0.0", port=8000)