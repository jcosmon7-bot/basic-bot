import os
import requests
import pandas as pd
import yfinance as yf
import time

# --- CONFIGURATION ---
SYMBOLS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "GC=F"
]
TIMEFRAME = "1d"    
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK') 

class ICT_Blueprint_Bot:
    def __init__(self, dataframe):
        self.df = dataframe.copy()
        self.swing_highs = [] 
        self.swing_lows = []
        self.market_structure = "NEUTRAL"
        self.current_range = None
        self.order_block = None
        self.fvg_zone = None 

    def calculate_indicators(self):
        if len(self.df) < 50: return 
        
        self.df['SMA_50'] = self.df['Close'].rolling(window=50).mean()

        for i in range(2, len(self.df)):
            self.identify_swings(i)
            self.check_market_structure(i)

    def identify_swings(self, i):
        try:
            h_i = float(self.df['High'].iloc[i])
            h_left = float(self.df['High'].iloc[i-1])
            h_left2 = float(self.df['High'].iloc[i-2])
            
            l_i = float(self.df['Low'].iloc[i])
            l_left = float(self.df['Low'].iloc[i-1])
            l_left2 = float(self.df['Low'].iloc[i-2])

            if h_left > h_left2 and h_left > h_i:
                self.swing_highs.append((i-1, h_left))
            
            if l_left < l_left2 and l_left < l_i:
                self.swing_lows.append((i-1, l_left))
        except Exception:
            pass

    def check_market_structure(self, i):
        if not self.swing_highs or not self.swing_lows: return
        
        current_close = float(self.df['Close'].iloc[i])
        current_sma = float(self.df['SMA_50'].iloc[i]) if not pd.isna(self.df['SMA_50'].iloc[i]) else 0
        
        last_high_idx, last_high_price = self.swing_highs[-1]
        last_low_idx, last_low_price = self.swing_lows[-1]

        if current_close > last_high_price and current_close > current_sma:
            if self.market_structure != "BULLISH":
                self.market_structure = "BULLISH"
                self.define_range("BULLISH")
        
        elif current_close < last_low_price or current_close < current_sma:
            if self.market_structure != "BEARISH":
                self.market_structure = "BEARISH"
                self.define_range("BEARISH")

    def define_range(self, direction):
        if direction == "BULLISH":
            recent_low_idx, recent_low = self.swing_lows[-1]
            highs = self.df['High'].iloc[recent_low_idx:]
            current_high = float(highs.max())
            mid = (current_high + recent_low) / 2
            
            self.current_range = {'discount': (recent_low, mid), 'dir': 'BULLISH'}
            self.find_order_block(recent_low_idx, "BULLISH")
            self.find_fvg(recent_low_idx, "BULLISH")

        elif direction == "BEARISH":
            recent_high_idx, recent_high = self.swing_highs[-1]
            lows = self.df['Low'].iloc[recent_high_idx:]
            current_low = float(lows.min())
            mid = (recent_high + current_low) / 2
            
            self.current_range = {'premium': (mid, recent_high), 'dir': 'BEARISH'}
            self.find_order_block(recent_high_idx, "BEARISH")
            self.find_fvg(recent_high_idx, "BEARISH")

    def find_order_block(self, pivot_index, direction):
        found_ob = False
        search_limit = 5 
        for k in range(search_limit):
            idx = pivot_index - k
            if idx < 0: break
            open_p = float(self.df['Open'].iloc[idx])
            close_p = float(self.df['Close'].iloc[idx])
            
            if direction == "BULLISH" and close_p < open_p: 
                self.order_block = {'top': float(self.df['High'].iloc[idx]), 'bottom': float(self.df['Low'].iloc[idx])}
                found_ob = True
                break
            elif direction == "BEARISH" and close_p > open_p: 
                self.order_block = {'top': float(self.df['High'].iloc[idx]), 'bottom': float(self.df['Low'].iloc[idx])}
                found_ob = True
                break
        if not found_ob:
            self.order_block = {'top': float(self.df['High'].iloc[pivot_index]), 'bottom': float(self.df['Low'].iloc[pivot_index])}

    def find_fvg(self, pivot_index, direction):
        self.fvg_zone = None 
        start_search = pivot_index
        end_search = min(len(self.df)-1, pivot_index + 5)
        
        for i in range(start_search, end_search):
            try:
                if direction == "BULLISH":
                    candle_1_high = float(self.df['High'].iloc[i])
                    candle_3_low = float(self.df['Low'].iloc[i+2])
                    if candle_3_low > candle_1_high: 
                        self.fvg_zone = {'top': candle_3_low, 'bottom': candle_1_high, 'type': 'Bullish FVG'}
                        return 

                elif direction == "BEARISH":
                    candle_1_low = float(self.df['Low'].iloc[i])
                    candle_3_high = float(self.df['High'].iloc[i+2])
                    if candle_1_low > candle_3_high: 
                        self.fvg_zone = {'top': candle_1_low, 'bottom': candle_3_high, 'type': 'Bearish FVG'}
                        return 
            except:
                continue

    def check_latest_signal(self, symbol_name):
        if not self.current_range: return None

        last_price = float(self.df['Close'].iloc[-1])
        last_low = float(self.df['Low'].iloc[-1])
        last_high = float(self.df['High'].iloc[-1])
        
        msg = None
        
        if self.current_range['dir'] == "BULLISH":
            if last_low < self.current_range['discount'][1]:
                if self.order_block and (self.order_block['bottom'] <= last_low <= self.order_block['top']):
                     msg = f"🚀 **BUY ALERT: {symbol_name}**\n**Setup:** Bullish Order Block + Discount\n**Price:** {last_price}\n**Ref:** Simple $10M Blueprint"
                elif self.fvg_zone and (self.fvg_zone['bottom'] <= last_low <= self.fvg_zone['top']):
                     msg = f"🚀 **BUY ALERT: {symbol_name}**\n**Setup:** Bullish FVG (Gap Fill) + Discount\n**Price:** {last_price}\n**Ref:** Simple $10M Blueprint"

        elif self.current_range['dir'] == "BEARISH":
            if last_high > self.current_range['premium'][0]:
                if self.order_block and (self.order_block['bottom'] <= last_high <= self.order_block['top']):
                    msg = f"📉 **SELL ALERT: {symbol_name}**\n**Setup:** Bearish Order Block + Premium\n**Price:** {last_price}\n**Ref:** Simple $10M Blueprint"
                elif self.fvg_zone and (self.fvg_zone['bottom'] <= last_high <= self.fvg_zone['top']):
                    msg = f"📉 **SELL ALERT: {symbol_name}**\n**Setup:** Bearish FVG (Gap Fill) + Premium\n**Price:** {last_price}\n**Ref:** Simple $10M Blueprint"
        
        return msg

def send_discord_alert(message):
    if not WEBHOOK_URL: return
    try:
        requests.post(WEBHOOK_URL, json={"content": message})
    except: pass

if __name__ == "__main__":
    print(f"Scanning {len(SYMBOLS)} assets...")
    for ticker in SYMBOLS:
        print(f"Checking {ticker}...", end=" ") # Visual feedback
        try:
            df = yf.download(ticker, period="1y", interval=TIMEFRAME, progress=False)
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if df.empty:
                print("❌ FAILED (No Data)")
                continue
            else:
                print(f"✅ Data OK ({len(df)} candles)", end=" - ")
                
            bot = ICT_Blueprint_Bot(df)
            bot.calculate_indicators() 
            signal = bot.check_latest_signal(ticker)
            
            if signal:
                print(f"SIGNAL FOUND! 🔔")
                send_discord_alert(signal)
            else:
                print("No Signal.")
            
            time.sleep(1)
        except Exception as e:
            print(f"❌ Error: {e}")
