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
        self.trend = "NEUTRAL" # Added for debugging

    def calculate_indicators(self):
        if len(self.df) < 50: return 
        
        # Calculate 50 SMA for Trend Filter
        self.df['SMA_50'] = self.df['Close'].rolling(window=50).mean()

        for i in range(2, len(self.df)):
            self.identify_swings(i)
            self.check_market_structure(i)

    def identify_swings(self, i):
        try:
            h_i = float(self.df['High'].iloc[i])
            h_i_1 = float(self.df['High'].iloc[i-1])
            h_i_2 = float(self.df['High'].iloc[i-2])
            
            l_i = float(self.df['Low'].iloc[i])
            l_i_1 = float(self.df['Low'].iloc[i-1])
            l_i_2 = float(self.df['Low'].iloc[i-2])

            # Swing High (Standard 3-candle pattern)
            if h_i_1 > h_i_2 and h_i_1 > h_i:
                self.swing_highs.append((i-1, h_i_1))
            
            # Swing Low
            if l_i_1 < l_i_2 and l_i_1 < l_i:
                self.swing_lows.append((i-1, l_i_1))
        except Exception:
            pass

    def check_market_structure(self, i):
        if not self.swing_highs or not self.swing_lows: return
        
        current_close = float(self.df['Close'].iloc[i])
        current_sma = float(self.df['SMA_50'].iloc[i]) if not pd.isna(self.df['SMA_50'].iloc[i]) else 0
        
        last_high_idx, last_high_price = self.swing_highs[-1]
        last_low_idx, last_low_price = self.swing_lows[-1]

        # Determine Trend based on SMA
        if current_close > current_sma:
            self.trend = "BULLISH"
        else:
            self.trend = "BEARISH"

        # Market Structure Break Logic
        if current_close > last_high_price:
            # ONLY flip bullish if we are also above 50 SMA
            if self.trend == "BULLISH" and self.market_structure != "BULLISH":
                self.market_structure = "BULLISH"
                self.define_range("BULLISH")
        
        elif current_close < last_low_price:
            # ONLY flip bearish if we are also below 50 SMA
            if self.trend == "BEARISH" and self.market_structure != "BEARISH":
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

        elif direction == "BEARISH":
            recent_high_idx, recent_high = self.swing_highs[-1]
            lows = self.df['Low'].iloc[recent_high_idx:]
            current_low = float(lows.min())
            mid = (recent_high + current_low) / 2
            self.current_range = {'premium': (mid, recent_high), 'dir': 'BEARISH'}
            self.find_order_block(recent_high_idx, "BEARISH")

    def find_order_block(self, pivot_index, direction):
        found_ob = False
        search_limit = 5 
        for k in range(search_limit):
            idx = pivot_index - k
            if idx < 0: break
            
            open_price = float(self.df['Open'].iloc[idx])
            close_price = float(self.df['Close'].iloc[idx])
            
            if direction == "BULLISH" and close_price < open_price: 
                self.order_block = {'top': float(self.df['High'].iloc[idx]), 'bottom': float(self.df['Low'].iloc[idx])}
                found_ob = True
                break
            elif direction == "BEARISH" and close_price > open_price: 
                self.order_block = {'top': float(self.df['High'].iloc[idx]), 'bottom': float(self.df['Low'].iloc[idx])}
                found_ob = True
                break
        if not found_ob:
            self.order_block = {'top': float(self.df['High'].iloc[pivot_index]), 'bottom': float(self.df['Low'].iloc[pivot_index])}

    def check_latest_signal(self, symbol_name):
        # DEBUG: Print status even if no signal
        last_price = float(self.df['Close'].iloc[-1])
        status_msg = f"   > Price: {last_price:.2f} | Trend (50SMA): {self.trend} | Structure: {self.market_structure}"
        print(status_msg)

        if not self.order_block or not self.current_range:
            print("   > No valid range or order block identified yet.")
            return None

        # Check latest completed candle
        last_low = float(self.df['Low'].iloc[-1])
        last_high = float(self.df['High'].iloc[-1])
        
        msg = None
        
        if self.current_range['dir'] == "BULLISH":
            # Debug info for bullish
            dist_to_ob = last_low - self.order_block['top']
            if dist_to_ob > 0:
                print(f"   > Bullish Setup: Waiting for price to drop {dist_to_ob:.2f} more to hit OB.")

            if last_low < self.current_range['discount'][1]: 
                if self.order_block['bottom'] <= last_low <= self.order_block['top']: 
                    msg = f"🚀 **BUY ALERT: {symbol_name}**\n**Bias:** BULLISH\n**Zone:** Discount + Order Block Tap\n**Price:** {last_price:.4f}\n**Action:** Check LTF for Breaker!"
        
        elif self.current_range['dir'] == "BEARISH":
            # Debug info for bearish
            dist_to_ob = self.order_block['bottom'] - last_high
            if dist_to_ob > 0:
                print(f"   > Bearish Setup: Waiting for price to rise {dist_to_ob:.2f} more to hit OB.")

            if last_high > self.current_range['premium'][0]: 
                if self.order_block['bottom'] <= last_high <= self.order_block['top']: 
                    msg = f"📉 **SELL ALERT: {symbol_name}**\n**Bias:** BEARISH\n**Zone:** Premium + Order Block Tap\n**Price:** {last_price:.4f}\n**Action:** Check LTF for Breaker!"
        
        return msg

def send_discord_alert(message):
    if not WEBHOOK_URL:
        print("No Webhook URL found.")
        return
    data = {"content": message}
    try:
        requests.post(WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"Failed to send alert: {e}")

if __name__ == "__main__":
    print(f"Starting Multi-Pair Scan ({len(SYMBOLS)} assets)...")
    
    for ticker in SYMBOLS:
        print(f"\n--- Analyzing {ticker} ---")
        try:
            df = yf.download(ticker, period="2y", interval=TIMEFRAME, progress=False)
            
            # Flatten MultiIndex Columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if df.empty:
                print(f"Skipping {ticker}: No data found.")
                continue
                
            bot = ICT_Blueprint_Bot(df)
            bot.calculate_indicators() 
            signal = bot.check_latest_signal(ticker)
            
            if signal:
                print(f"✅ SIGNAL FOUND for {ticker}")
                send_discord_alert(signal)
            
        except Exception as e:
            print(f"⚠️ Error analyzing {ticker}: {e}")
            
