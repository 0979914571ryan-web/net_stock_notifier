import sqlite3
import yfinance as yf
from datetime import datetime

def init_test_db():
    """
    初始化資料庫。
    這裡強制指定一個全新的檔名 'portfolio_new.db'，
    確保它一定會寫入硬碟，並採用我們最新定義的表格結構。
    """
    # 🌟 修改這裡：指定一個實體的檔案名稱，而不是 ':memory:'
    conn = sqlite3.connect('portfolio_new.db')
    
    # ... (你原本 init_test_db 裡面的建表與假資料寫入邏輯，請保留原本的內容)
    # ... 為了保險起見，我把完整的建表邏輯再給你一次，請確保你的程式碼長這樣：
    
    cursor = conn.cursor()
    # 建立 User 表格
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            user_id TEXT PRIMARY KEY
        )
    ''')
    
    # 🌟 最關鍵的一步：建立包含 'date' 欄位的 Transactions 表格
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            date TEXT,
            type TEXT,
            stock_code TEXT,
            shares INTEGER,
            price REAL,
            fee REAL,
            FOREIGN KEY (user_id) REFERENCES Users(user_id)
        )
    ''')
    
    # --- 以下是你原本插入假資料的程式碼，可以保留 ---
    # cursor.execute("INSERT OR IGNORE INTO Users (user_id) VALUES ('U_TEST_123')")
    # ...
    
    conn.commit()
    return conn

def fetch_current_prices(stock_codes):
    prices = {}
    if not stock_codes: return prices
    tickers = " ".join(stock_codes)
    data = yf.download(tickers, period="1d", progress=False)
    if len(stock_codes) == 1:
        prices[stock_codes[0]] = float(data['Close'].iloc[0])
    else:
        for code in stock_codes:
            prices[code] = float(data['Close'][code].iloc[0])
    return prices

def calculate_portfolio(conn, user_id):
    cursor = conn.cursor()
    cursor.execute("SELECT fee_discount, margin_rate FROM users WHERE user_id = ?", (user_id,))
    discount, margin_rate = cursor.fetchone()
    
    cursor.execute("SELECT stock_code, account_type, shares, buy_price, trade_date FROM transactions WHERE user_id = ?", (user_id,))
    trades = cursor.fetchall()
    
    unique_codes = list(set([t[0] for t in trades]))
    current_prices = fetch_current_prices(unique_codes)
    
    portfolio_details = []
    # 新增融資本金、利息與稅費的獨立欄位
    summary = {"總資產": 0.0, "淨資產": 0.0, "負債": 0.0, "融資本金": 0.0, "利息與稅費": 0.0}
    today = datetime.now()
    
    for code, acc_type, shares, buy_price, trade_date in trades:
        cur_price = current_prices.get(code, buy_price)
        days_held = max(1, (today - datetime.strptime(trade_date, "%Y-%m-%d")).days)
        market_value = cur_price * shares
        
        sell_fee = market_value * 0.001425 * discount
        sell_tax = market_value * 0.003
        accrued_fees = sell_fee + sell_tax
        
        if acc_type == '現股':
            liability = accrued_fees
            net_value = market_value - liability
            
            summary["利息與稅費"] += accrued_fees
            
        elif acc_type == '融資':
            margin_loan = buy_price * shares * 0.6          
            margin_interest = margin_loan * margin_rate * (days_held / 365) 
            
            liability = margin_loan + margin_interest + accrued_fees
            net_value = market_value - liability
            
            summary["融資本金"] += margin_loan
            summary["利息與稅費"] += (margin_interest + accrued_fees)
            
        summary["總資產"] += market_value
        summary["淨資產"] += net_value
        summary["負債"] += liability
        
        portfolio_details.append({
            "代號": code.split('.')[0],
            "類型": acc_type,
            "股數": shares,
            "現價": cur_price,
            "市值": market_value,
            "淨值": net_value
        })
        
    return summary, portfolio_details

if __name__ == "__main__":
    print("核心引擎運作中...")

def insert_trade_record(conn, user_id, trade_date, trade_type, stock_code, shares, price):
    """
    將使用者的交易紀錄新增至資料庫
    """
    cursor = conn.cursor()
    
    # 檢查使用者是否存在
    cursor.execute("SELECT user_id FROM Users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO Users (user_id) VALUES (?)", (user_id,))
    
    # 寫入交易紀錄 (確保欄位對應正確)
    cursor.execute("""
        INSERT INTO Transactions 
        (user_id, date, type, stock_code, shares, price, fee)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (user_id, trade_date, trade_type, stock_code, shares, price))
    
    conn.commit()
    print(f"✅ 已成功新增一筆交易: {trade_type} {stock_code} {shares}股 @ {price}")

    