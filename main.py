import time
import threading
from flask import Flask
from pybit.unified_trading import HTTP
import pandas as pd
import ta
import datetime
import sys
sys.stdout.reconfigure(line_buffering=True)

# Bybit API 설정
api_key = "b3b9DkGWQaf3XOapet"
api_secret = "sgQjqo3ocsVD0aN4Wws8pE9AGU5EpuFVLijJ"
symbol = "BTCUSDT"
leverage = 25

session = HTTP(api_key=api_key, api_secret=api_secret)
app = Flask(__name__)

def set_leverage():
    try:
        session.set_leverage(category="linear", symbol=symbol, buyLeverage=leverage, sellLeverage=leverage)
    except Exception as e:
        if "not modified" in str(e) or "ErrCode: 10001" in str(e):
            print("⚠️ 레버리지는 이미 설정되어 있거나 유니파이드 계정에서는 변경 불가능합니다.")
        else:
            print("❌ 레버리지 설정 실패:", e)

def get_balance():
    res = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
    return float(res["result"]["list"][0]["totalWalletBalance"])

def get_candles():
    try:
        res = session.get_kline(category="linear", symbol=symbol, interval="5", limit=200)
        data = res['result']['list']
        df = pd.DataFrame(data)
        df.columns = ['timestamp','open','high','low','close','volume','turnover']
        df = df.iloc[::-1]
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        print(f"❌ 캔들 조회 실패: {e}")
        return pd.DataFrame()

def get_current_price():
    try:
        res = session.get_tickers(category="linear", symbol=symbol)
        return float(res['result']['list'][0]['markPrice'])
    except Exception as e:
        print(f"❌ 현재가 조회 실패: {e}")
        return 0

def get_ema(df, period):
    return ta.trend.ema_indicator(df["close"], period).fillna(0)

def get_quantity():
    usdt = get_balance()
    if usdt == 0:
        return 0
    price = get_current_price()
    qty = round((usdt * leverage) / price, 3)
    return qty

def get_position():
    try:
        res = session.get_positions(category="linear", symbol=symbol)
        for pos in res["result"]["list"]:
            if float(pos["size"]) > 0:
                return pos
        return None
    except Exception as e:
        print("❌ 포지션 조회 실패:", e)
        return None

def cancel_orders():
    try:
        session.cancel_all_orders(category="linear", symbol=symbol)
    except Exception as e:
        print("❌ 주문 취소 실패:", e)

def place_order(side, qty, tp, sl):
    try:
        session.place_order(
            category="linear", symbol=symbol,
            side=side,
            order_type="Market",
            qty=qty,
            time_in_force="GoodTillCancel",
            reduce_only=False,
            takeProfit=round(tp, 1),
            stopLoss=round(sl, 1)
        )
        print(f"✅ {side} 진입. TP: {tp}, SL: {sl}")
    except Exception as e:
        print(f"❌ {side} 주문 실패:", e)

def run_bot():
    set_leverage()
    pos = None
    while True:
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 봇 작동 중...")  # ✅ 여기에 한 줄 추가
        df = get_candles()
        if df.empty:
            time.sleep(60)
            continue

        df["EMA20"] = get_ema(df, 20)
        df["EMA50"] = get_ema(df, 50)
        df["EMA100"] = get_ema(df, 100)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = get_current_price()
        ema20, ema50, ema100 = latest["EMA20"], latest["EMA50"], latest["EMA100"]

        pos = get_position()
        print(f"🔄 조건 확인 중 | 현재가: {price:.1f}, 포지션: {'보유 중' if pos else '없음'}")
        print(f"📊 EMA 배열: EMA20({ema20:.1f}), EMA50({ema50:.1f}), EMA100({ema100:.1f})")
        print(f"[1] 현재가: {price}, EMA20: {ema20}, EMA50: {ema50}, EMA100: {ema100}")
        print(f"[2] 💰 USDT 잔고: {get_balance()}")

#        if pos:
#            entry_price = float(pos["entryPrice"])
#            side = pos["side"]
#            stop_loss = ema50
#
#            if side == "Buy" and price < stop_loss:
#                cancel_orders()
#                session.place_order(category="linear", symbol=symbol, side="Sell", order_type="Market", qty=pos["size"], time_in_force="GoodTillCancel", reduce_only=True,position_idx=1)
#                print("🔻 롱 포지션 손절")
#
#            elif side == "Sell" and price > stop_loss:
#                cancel_orders()
#                session.place_order(category="linear", symbol=symbol, side="Buy", order_type="Market", qty=pos["size"], time_in_force="GoodTillCancel", reduce_only=True,position_idx=1)
#                print("🔺 숏 포지션 손절")

        else:
            if ema20 > ema50 > ema100 and prev["close"] < prev["EMA20"] and latest["close"] > ema20:
                if abs(price - ema50) / price > 0.001:
                    qty = get_quantity()
                    print("🧮 진입 수량:", qty)
                    if qty == 0:
                        print("⛔ 진입 수량이 0입니다.")
                        time.sleep(60)
                        continue
                    tp = price + (price - ema50) * 1.5
                    sl = ema50
                    place_order("Buy", qty, tp, sl)

            elif ema20 < ema50 < ema100 and prev["close"] > prev["EMA20"] and latest["close"] < ema20:
                if abs(price - ema50) / price > 0.001:
                    qty = get_quantity()
                    print("🧮 진입 수량:", qty)
                    if qty == 0:
                        print("⛔ 진입 수량이 0입니다.")
                        time.sleep(60)
                        continue
                    tp = price - (ema50 - price) * 1.5
                    sl = ema50
                    place_order("Sell", qty, tp, sl)

        time.sleep(60)

@app.route('/')
def home():
    return "Bybit BTCUSDT 자동매매 봇이 실행 중입니다."

if __name__ == '__main__':
    t = threading.Thread(target=run_bot)
    t.start()
    app.run(host='0.0.0.0', port=8080)
    