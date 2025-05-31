"""
SOUN Cycle Bot: Buy 1 share → DCA based on that price → Repeat cycle
"""

import os
from dotenv import load_dotenv
import alpaca_trade_api as tradeapi
import json
from datetime import datetime
import time

load_dotenv()

class SOUNCycleBot:
    def __init__(self):
        self.api = tradeapi.REST(
            os.getenv('ALPACA_API_KEY'),
            os.getenv('ALPACA_SECRET_KEY'),
            os.getenv('ALPACA_BASE_URL'),
            api_version='v2'
        )
        self.symbol = 'SOUN'
        self.dca_amount = 20.0
        
        # Load saved data
        try:
            with open('soun_cycle_data.json', 'r') as f:
                self.data = json.load(f)
                # Add new fields if they don't exist (for existing data files)
                if 'trades_today' not in self.data:
                    self.data['trades_today'] = 0
                if 'last_trade_date' not in self.data:
                    self.data['last_trade_date'] = None
        except:
            self.data = {
                'last_single_share_price': None,  # Price of last single share bought
                'total_invested': 0.0,
                'total_shares': 0.0,
                'waiting_for_dca': False,  # Are we in DCA mode for current price level?
                'trades_today': 0,
                'last_trade_date': None
            }
    
    def save_data(self):
        with open('soun_cycle_data.json', 'w') as f:
            json.dump(self.data, f)
    
    def check_daily_trade_limit(self):
        """Check if we can still trade today (max 2 trades)"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Reset counter if new day
        if self.data['last_trade_date'] != today:
            self.data['trades_today'] = 0
            self.data['last_trade_date'] = today
            self.save_data()
        
        if self.data['trades_today'] >= 2:
            return False, f"Daily limit reached: {self.data['trades_today']}/2 trades"
        else:
            return True, f"Trades today: {self.data['trades_today']}/2"
    
    def record_trade(self):
        """Record that a trade was made"""
        self.data['trades_today'] += 1
        self.save_data()
    
    def get_balance(self):
        account = self.api.get_account()
        return float(account.buying_power)
    
    def has_sufficient_funds(self, balance, needed_amount):
        """Check if we have enough money to continue"""
        if balance >= needed_amount:
            return True
        else:
            print(f"\n🚨 INSUFFICIENT FUNDS - BOT STOPPING!")
            print(f"   Need: ${needed_amount:.2f}")
            print(f"   Have: ${balance:.2f}")
            print(f"   ADD: ${needed_amount - balance:.2f}")
            print(f"🛑 Bot will stop until funds are added...")
            return False
    
    def is_market_open(self):
        """Check if market is open"""
        try:
            clock = self.api.get_clock()
            return clock.is_open
        except:
            return False
    def get_price(self):
        quote = self.api.get_latest_quote(self.symbol)
        return quote.ask_price or quote.bid_price
    
    def buy_single_share(self, current_price):
        """Buy 1 share at current price"""
        print(f"🎯 BUYING 1 SHARE @ ${current_price:.2f}")
        
        try:
            order = self.api.submit_order(
                symbol=self.symbol,
                qty=1,
                side='buy',
                type='market',
                time_in_force='day'
            )
            
            print(f"✅ Single share order: {order.id}")
            
            # Update tracking
            self.data['last_single_share_price'] = current_price
            self.data['total_invested'] += current_price
            self.data['total_shares'] += 1.0
            self.data['waiting_for_dca'] = True
            self.record_trade()  # Count this trade
            
            self.save_data()
            print(f"✅ SINGLE SHARE BOUGHT @ ${current_price:.2f}")
            print(f"🔄 Now waiting for price below ${current_price:.2f} to DCA")
            return True
            
        except Exception as e:
            print(f"❌ Single share order failed: {e}")
            return False
    
    def dca_buy(self, current_price):
        """DCA buy at current price"""
        shares = self.dca_amount / current_price
        
        print(f"📈 DCA BUY: {shares:.3f} shares @ ${current_price:.2f}")
        
        try:
            order = self.api.submit_order(
                symbol=self.symbol,
                qty=shares,
                side='buy',
                type='market',
                time_in_force='day'
            )
            
            print(f"✅ DCA order: {order.id}")
            
            # Update tracking
            self.data['total_invested'] += self.dca_amount
            self.data['total_shares'] += shares
            self.record_trade()  # Count this trade
            
            self.save_data()
            print(f"✅ DCA COMPLETE: {shares:.3f} shares @ ${current_price:.2f}")
            return True
            
        except Exception as e:
            print(f"❌ DCA order failed: {e}")
            return False
    
    def run(self):
        """Main bot cycle logic"""
        print("🔄 SOUN CYCLE BOT RUNNING...")
        print("=" * 50)
        
        balance = self.get_balance()
        current_price = self.get_price()
        
        print(f"💰 Balance: ${balance:.2f}")
        print(f"📊 SOUN: ${current_price:.2f}")
        
        # Check daily trade limit
        can_trade, trade_msg = self.check_daily_trade_limit()
        print(f"📈 {trade_msg}")
        
        if not can_trade:
            print("🛑 Daily trade limit reached, waiting for tomorrow")
            return
        
        # CYCLE LOGIC:
        
        # If no previous single share OR not waiting for DCA = BUY 1 SHARE
        if not self.data['waiting_for_dca']:
            print("🎯 CYCLE: Time to buy 1 share")
            if balance >= current_price:
                self.buy_single_share(current_price)
            else:
                print(f"🚨 INSUFFICIENT FUNDS!")
                print(f"   Need: ${current_price:.2f} for 1 share")
                print(f"   Have: ${balance:.2f}")
        
        # If waiting for DCA = check if price dropped below last single share price
        else:
            last_price = self.data['last_single_share_price']
            print(f"🔄 CYCLE: Waiting for price below ${last_price:.2f}")
            
            if current_price < last_price:
                print(f"✅ PRICE DROPPED! ${current_price:.2f} < ${last_price:.2f}")
                
                if balance >= self.dca_amount:
                    if self.dca_buy(current_price):
                        # After DCA, reset cycle to buy 1 share again
                        self.data['waiting_for_dca'] = False
                        self.save_data()
                        print("🔄 CYCLE RESET: Ready to buy next single share")
                else:
                    print(f"🚨 INSUFFICIENT FUNDS!")
                    print(f"   Need: ${self.dca_amount:.2f} for DCA")
                    print(f"   Have: ${balance:.2f}")
            else:
                print(f"⏳ WAITING: Current ${current_price:.2f} >= Last ${last_price:.2f}")
                print("   No action until price drops")
        
        # Show position
        if self.data['total_shares'] > 0:
            current_value = self.data['total_shares'] * current_price
            pnl = current_value - self.data['total_invested']
            avg_cost = self.data['total_invested'] / self.data['total_shares']
            
            print(f"\n📊 TOTAL POSITION:")
            print(f"   Shares: {self.data['total_shares']:.3f}")
            print(f"   Invested: ${self.data['total_invested']:.2f}")
            print(f"   Avg Cost: ${avg_cost:.2f}")
            print(f"   Current Value: ${current_value:.2f}")
            print(f"   P&L: ${pnl:.2f} ({(pnl/self.data['total_invested']*100):+.1f}%)")
            
            if self.data['waiting_for_dca']:
                print(f"\n🎯 NEXT ACTION: DCA when price < ${self.data['last_single_share_price']:.2f}")
            else:
                print(f"\n🎯 NEXT ACTION: Buy 1 share at current price")

if __name__ == "__main__":
    bot = SOUNCycleBot()
    
    while True:
        try:
            bot.run()
            print("\n⏳ Waiting 1 minute...")
            time.sleep(60)  # Wait 1 minute
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped by user")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("⏳ Retrying in 1 minute...")
            time.sleep(60)
