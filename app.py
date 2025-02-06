from flask import Flask, jsonify
from flask_cors import CORS  # Import CORS
from pymongo import MongoClient
import yfinance as yf
import os
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app) # Enable CORS for all routes - this is important for local development

# MongoDB Connection URI from environment variable
mongo_uri = os.environ.get('MONGODB_URI')

if not mongo_uri:
    print("Error: MONGODB_URI environment variable not set.")
    exit(1)

client = MongoClient(mongo_uri)
db = client['trading']  # Database name is 'trading' as per your rules

# Cache for stock prices
price_cache = {}
CACHE_DURATION = timedelta(minutes=5)  # Cache data for 5 minutes

def get_stock_prices(symbols):
    """Helper function to get real-time prices for multiple symbols with caching"""
    prices = {}
    symbols_to_fetch = []
    current_time = datetime.now()
    
    if symbols:
        # First check cache for valid entries
        for symbol in symbols:
            if symbol == 'cash':
                continue
            if symbol in price_cache:
                cached_data = price_cache[symbol]
                if current_time - cached_data['timestamp'] < CACHE_DURATION:
                    prices[symbol] = cached_data['data']
                    print(f"Using cached data for {symbol}")
                else:
                    symbols_to_fetch.append(symbol)
            else:
                symbols_to_fetch.append(symbol)
        
        # Only fetch new data for symbols not in cache
        if symbols_to_fetch:
            try:
                print(f"Fetching fresh data for: {symbols_to_fetch}")
                tickers = yf.Tickers(' '.join(symbols_to_fetch))
                for symbol in symbols_to_fetch:
                    try:
                        ticker = tickers.tickers[symbol]
                        info = ticker.fast_info
                        
                        current_price = getattr(info, 'last_price', None)
                        previous_close = getattr(info, 'previous_close', None)
                        
                        is_market_closed = current_price is None or current_price == 0
                        price = previous_close if is_market_closed else current_price
                        
                        price_data = {
                            'price': price if price is not None else 0,
                            'change': 0,
                            'changePercent': 0,
                            'previousClose': previous_close if previous_close is not None else 0,
                            'isMarketClosed': is_market_closed
                        }
                        
                        # Cache the new data
                        price_cache[symbol] = {
                            'timestamp': current_time,
                            'data': price_data
                        }
                        prices[symbol] = price_data
                        
                    except Exception as e:
                        print(f"Error fetching {symbol}: {str(e)}")
                        prices[symbol] = {
                            'price': 0,
                            'change': 0,
                            'changePercent': 0,
                            'previousClose': 0,
                            'isMarketClosed': True
                        }
            except Exception as e:
                print(f"Error in batch price fetch: {str(e)}")
    
    return prices

@app.route('/watchlist')
def get_watchlist():
    try:
        watchlist_data = list(db.watchlist.find({}, {'_id': 0}))
        
        if watchlist_data and 'sector_watchlists' in watchlist_data[0]:
            sectors = watchlist_data[0]['sector_watchlists']
            all_symbols = []
            
            # Get all unique symbols while preserving order
            for sector, stocks in sectors.items():
                if isinstance(stocks, list):
                    all_symbols.extend([stock for stock in stocks if stock and isinstance(stock, str)])
            
            # Remove duplicates while preserving order
            all_symbols = list(dict.fromkeys(all_symbols))
            
            if all_symbols:
                print(f"Fetching prices for {len(all_symbols)} symbols...")
                prices = get_stock_prices(all_symbols)
                watchlist_data[0]['prices'] = prices
        
        return jsonify(watchlist=watchlist_data)
    except Exception as e:
        print(f"Error in watchlist: {str(e)}")
        return jsonify({'error': 'Failed to fetch watchlist data'}), 500

@app.route('/trades')
def get_trades():
    print("Request received for /trades") # Debug log
    trades_data = list(db.trades.find({}, {'_id': 0})) # Fetch trades data, exclude _id
    print(f"Trades data fetched: {trades_data}") # Debug log
    return jsonify(trades=trades_data)

@app.route('/bot_settings')
def get_bot_settings():
    print("Request received for /bot_settings") # Debug log
    settings_data = db.bot_settings.find_one({}, {'_id': 0})
    print(f"Bot settings data fetched: {settings_data}") # Debug log
    if settings_data:
        return jsonify(bot_settings=settings_data)
    else:
        return jsonify(error="Bot settings not found"), 404

@app.route('/summary')
def get_summary():
    try:
        summary_data = db.summary.find_one({}, {'_id': 0})
        if summary_data:
            # Get current holdings from portfolio
            portfolio = summary_data.get('portfolio', {})
            
            # Get cash balance from the root level 'balance' field
            cash_balance = float(summary_data.get('balance', 0))  # Get balance from root level
            print(f"Initial cash balance: ${cash_balance:.2f}")
            
            # Get purchase prices from trades collection
            purchase_prices = {}
            holdings_with_value = {}
            total_value = cash_balance  # Start with cash
            total_cost_basis = cash_balance  # Include initial cash in cost basis
            
            # Process each holding
            for symbol, shares in portfolio.items():
                if symbol == 'cash':
                    continue
                
                # Get the purchase price from the last BUY trade
                last_buy = db.trades.find_one(
                    {'ticker': symbol, 'action': 'BUY'},
                    {'price': 1},
                    sort=[('timestamp', -1)]
                )
                purchase_price = last_buy['price'] if last_buy else 0
                
                # Get current price
                current_price_data = get_stock_prices([symbol])
                current_price = current_price_data.get(symbol, {}).get('price', 0)
                
                # Calculate values
                shares = float(shares)
                current_value = current_price * shares
                cost_basis = purchase_price * shares
                unrealized_pl = current_value - cost_basis
                pl_percentage = ((current_price - purchase_price) / purchase_price * 100) if purchase_price > 0 else 0
                
                total_value += current_value
                total_cost_basis += cost_basis
                
                holdings_with_value[symbol] = {
                    'shares': shares,
                    'purchase_price': purchase_price,
                    'current_price': current_price,
                    'current_value': current_value,
                    'cost_basis': cost_basis,
                    'unrealized_pl': unrealized_pl,
                    'pl_percentage': pl_percentage
                }
            
            # Update summary with calculated values
            summary_data['portfolio_details'] = holdings_with_value
            summary_data['total_portfolio_value'] = total_value
            summary_data['cash_balance'] = cash_balance
            summary_data['total_cost_basis'] = total_cost_basis
            summary_data['total_unrealized_pl'] = total_value - total_cost_basis
            summary_data['total_pl_percentage'] = ((total_value - total_cost_basis) / total_cost_basis * 100) if total_cost_basis > 0 else 0
            
            # Debug prints
            print(f"Total Portfolio Value: ${total_value:.2f}")
            print(f"Total Cost Basis: ${total_cost_basis:.2f}")
            print(f"Cash Balance: ${cash_balance:.2f}")
            print(f"Total P/L: ${summary_data['total_unrealized_pl']:.2f}")
            
            return jsonify(summary=summary_data)
    except Exception as e:
        print(f"Error in summary: {str(e)}")
        return jsonify({'error': 'Failed to fetch summary data'}), 500

@app.route('/stock_price/<symbol>')
def get_stock_price(symbol):
    try:
        # Fetch real-time data from yfinance
        stock = yf.Ticker(symbol)
        # Get the current price data
        current = stock.info
        
        price_data = {
            'symbol': symbol,
            'price': current.get('regularMarketPrice', 0),
            'change': current.get('regularMarketChange', 0),
            'changePercent': current.get('regularMarketChangePercent', 0)
        }
        
        return jsonify(price_data)
    except Exception as e:
        print(f"Error fetching price for {symbol}: {str(e)}")
        return jsonify({'error': f'Failed to fetch price for {symbol}'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000) # Run Flask app on port 5000 