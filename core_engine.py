import sqlite3
import yfinance as yf
from datetime import datetime

def init_test_db():
    conn = sqlite3.connect('portfolio_new.db')
    cursor = conn.cursor()
    
    # 1. 建立基本的 Users 表格
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            user_id TEXT PRIMARY KEY
        )
    ''')
    
    # 2. 自動升級資料庫與設定預設值
    try:
        cursor.execute("ALTER TABLE Users ADD COLUMN fee_discount REAL DEFAULT 1.0")
    except sqlite3.OperationalError:
        pass 
        
    try:
        # 將新建立欄位的預設值改為 0.064 (6.4%)
        cursor.execute("ALTER TABLE Users ADD COLUMN margin_rate REAL DEFAULT 0.064")
    except sqlite3.OperationalError:
        pass

    # 🌟 強制將資料庫中所有現有用戶的融資利率更新為 6.4%
    cursor.execute("UPDATE Users SET margin_rate = 0.064")

    # 3. 建立交易紀錄表格
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
    conn.commit()
    return conn

def fetch_current_prices(stock_codes):
    prices = {}
    if not stock_codes: return prices
    
    tickers = " ".join([f"{c}.TW" if not c.endswith(('.TW','.TWO')) else c for c in stock_codes])
    
    try:
        data = yf.download(tickers, period="1d", progress=False)
        for code in stock_codes:
            try:
                ticker_str = f"{code}.TW" if not code.endswith(('.TW','.TWO')) else code
                if len(stock_codes) == 1:
                    if not data.empty and 'Close' in data:
                        prices[code] = float(data['Close'].iloc[-1])
                else:
                    if not data.empty and 'Close' in data and ticker_str in data['Close']:
                        prices[code] = float(data['Close'][ticker_str].iloc[-1])
            except Exception:
                pass 
    except Exception as e:
        print("yfinance 抓取發生錯誤:", e)
        
    return prices

def calculate_portfolio(conn, user_id):
    cursor = conn.cursor()
    
    cursor.execute("SELECT fee_discount, margin_rate FROM Users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    if user_row:
        discount, margin_rate = user_row
    else:
        # 找不到用戶時的防呆預設值也改為 0.064 (6.4%)
        discount, margin_rate = 1.0, 0.064
        
    cursor.execute("SELECT stock_code, type, shares, price, date FROM Transactions WHERE user_id = ?", (user_id,))
    trades = cursor.fetchall()
    
    unique_codes = list(set([t[0] for t in trades]))
    current_prices = fetch_current_prices(unique_codes)
    
    portfolio_details = []
    summary = {"總資產": 0.0, "淨資產": 0.0, "負債": 0.0, "融資本金": 0.0, "利息與稅費": 0.0}
    today = datetime.now()
    
    for code, acc_type, shares, buy_price, trade_date in trades:
        cur_price = current_prices.get(code, buy_price)
        
        try:
            trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")
        except ValueError:
            trade_dt = today
        days_held = max(1, (today - trade_dt).days)
        
        market_value = cur_price * shares
        
        if acc_type == '現股':
            liability = 0
            net_value = market_value
            
        elif acc_type == '融資':
            sell_fee = market_value * 0.001425 * discount
            sell_tax = market_value * 0.003
            accrued_fees = sell_fee + sell_tax
            
            margin_loan = buy_price * shares * 0.6          
            # 這裡會使用剛剛抓取到的 margin_rate (6.4%) 來計算利息
            margin_interest = margin_loan * margin_rate * (days_held / 365) 
            
            liability = margin_loan + margin_interest + accrued_fees
            net_value = market_value - liability
            
            summary["融資本金"] += margin_loan
            summary["利息與稅費"] += (margin_interest + accrued_fees)
            
        else:
            liability, net_value = 0, market_value
            
        summary["總資產"] += market_value
        summary["淨資產"] += net_value
        summary["負債"] += liability
        
        portfolio_details.append({
            "代號": str(code).split('.')[0], 
            "類型": acc_type, 
            "股數": shares, 
            "現價": cur_price, 
            "淨值": net_value
        })
        
    return summary, portfolio_details

def insert_trade_record(conn, user_id, trade_date, trade_type, stock_code, shares, price):
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM Users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        # 第一次新增用戶時，寫入的預設值改為 0.064
        cursor.execute("INSERT INTO Users (user_id, fee_discount, margin_rate) VALUES (?, 1.0, 0.064)", (user_id,))
    
    cursor.execute("""
        INSERT INTO Transactions (user_id, date, type, stock_code, shares, price, fee)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (user_id, trade_date, trade_type, stock_code, shares, price))
    conn.commit()