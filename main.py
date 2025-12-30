import os
import requests
import pandas as pd
import yfinance as yf

# --- CONFIGURATION ---
SYMBOL = "BTC-USD" 
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

    def calculate_indicators(self):
        # ERROR FIX 1: Start loop at 2 to avoid negative index (i-2)
        if len(self.df) < 20: return # Not enough data
        
        for i in range(2, len(self.df)):
            self.identify_swings(i)
            self.check_market_structure(i)

    def identify_swings(self, i):
        # Swing High: High[i-1] > High[i-2] AND High[i-1] > High[i]
        if (self.df['High'].iloc[i-1] > self.df['High'].iloc[i-2] and 
            self.df['High'].iloc[i-1] > self.df['High'].iloc[i]):
            self.swing_highs.append((i-1, self.df['High'].iloc[i-1]))
        
        # Swing Low: Low[i-1] < Low[i-2] AND Low[i-1] < Low[i]
        if (self.df['Low'].iloc[i-1] < self.df['Low'].iloc[i-2] and 
            self.df['Low'].iloc[i-1] < self.df['Low'].iloc[i]):
            self.swing_lows.append((i-1, self.df['Low'].iloc[i-1]))

    def check_market_structure(self, i):
        if not self.swing_highs or not self.swing_lows: return
        
        current_close = self.df['Close'].iloc[i]
        last_high_idx, last_high_price = self.swing_highs[-1]
        last_low_idx, last_low_price = self.swing_lows[-1]

        # Bullish Break (Body Close > Last Swing High)
        if current_close > last_high_price and self.market_structure != "BULLISH":
            self.market_structure = "BULLISH"
            self.define_range("BULLISH")
        
        # Bearish Break (Body Close < Last Swing Low)
        elif current_close < last_low_price and self.market_structure != "BEARISH":
            self.market_structure = "BEARISH"
            self.define_range("BEARISH")

    def define_range(self, direction):
        if direction == "BULLISH":
            # Range is from Last Swing Low -> Current High
            recent_low_idx, recent_low = self.swing_lows[-1]
            current_high = self.df['High'].iloc[recent_low_idx:].max()
            
            mid = (current_high + recent_low) / 2
            self.current_range = {'discount': (recent_low, mid), 'dir': 'BULLISH'}
            
            # ERROR FIX 3: Find REAL Order Block (Last Down Candle)
            self.find_order_block(recent_low_idx, "BULLISH")

        elif direction == "BEARISH":
            recent_high_idx, recent_high = self.swing_highs[-1]
            current_low = self.df['Low'].iloc[recent_high_idx:].min()
            
            mid = (recent_high + current_low) / 2
            self.current_range = {'premium': (mid, recent_high), 'dir': 'BEARISH'}
            
            # ERROR FIX 3: Find REAL Order Block (Last Up Candle)
            self.find_order_block(recent_high_idx, "BEARISH")

    def find_order_block(self, pivot_index, direction):
        # Search backwards 5 candles from pivot to find the right color
        # Bullish OB = Last RED (Down) candle
        # Bearish OB = Last GREEN (Up) candle
        
        found_ob = False
        search_limit = 5 
        
        for k in range(search_limit):
            idx = pivot_index - k
            if idx < 0: break
            
            open_price = self.df['Open'].iloc[idx]
            close_price = self.df['Close'].iloc[idx]
            
            if direction == "BULLISH" and close_price < open_price: # Red Candle
                self.order_block = {'top': self.df['High'].iloc[idx], 'bottom': self.df['Low'].iloc[idx]}
                found_ob = True
                break
            elif direction == "BEARISH" and close_price > open_price: # Green Candle
                self.order_block = {'top': self.df['High'].iloc[idx], 'bottom': self.df['Low'].iloc[idx]}
                found_ob = True
                break
        
        # Fallback: If no clear OB found, use the pivot candle itself
        if not found_ob:
            self.order_block = {'top': self.df['High'].iloc[pivot_index], 'bottom': self.df['Low'].iloc[pivot_index]}

    def check_latest_signal(self):
        if not self.order_block or not self.current_range:
            return None

        # Check yesterday's fully closed candle (iloc[-1] is typically today's live candle if market is open)
        # For safety in Daily timeframe, we look at iloc[-1] assuming we run this AFTER close
        last_price = self.df['Close'].iloc[-1]
        last_low = self.df['Low'].iloc[-1]
        last_high = self.df['High'].iloc[-1]
        
        msg = None
        if self.current_range['dir'] == "BULLISH":
            # Price dipped into Discount (< 50%) AND touched Order Block
            if last_low < self.current_range['discount'][1]: 
                if self.order_block['bottom'] <= last_low <= self.order_block['top']: 
                    msg = f"🚀 **BUY ALERT (BTC)** \n**Bias:** BULLISH\n**Zone:** Discount + Order Block Tap\n**Action:** Check LTF for Breaker!"
        
        elif self.current_range['dir'] == "BEARISH":
            # Price rallied into Premium (> 50%) AND touched Order Block
            if last_high > self.current_range['premium'][0]: 
                if self.order_block['bottom'] <= last_high <= self.order_block['top']: 
                    msg = f"📉 **SELL ALERT (BTC)** \n**Bias:** BEARISH\n**Zone:** Premium + Order Block Tap\n**Action:** Check LTF for Breaker!"
        
        return msg

def send_discord_alert(message):
    if not WEBHOOK_URL:
        print("No Webhook URL found. Check GitHub Secrets.")
        return
    # Add a cool color or avatar if you want later, keeping it simple for now
    data = {"username": "ICT Bot", "content": message}
    try:
        requests.post(WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"Failed to send alert: {e}")

if __name__ == "__main__":
    print(f"Fetching data for {SYMBOL}...")
    
    # ERROR FIX 2: Handle empty data
    try:
        df = yf.download(SYMBOL, period="2y", interval=TIMEFRAME, progress=False)
        if df.empty:
            print("Error: DataFrame is empty. Ticker might be wrong or API down.")
            exit()
    except Exception as e:
        print(f"Error downloading data: {e}")
        exit()

    bot = ICT_Blueprint_Bot(df)
    bot.calculate_indicators() 
    
    signal = bot.check_latest_signal()
    
    if signal:
        print("Signal Found! Sending Alert...")
        send_discord_alert(signal)
    else:
        print("No signal today.")
