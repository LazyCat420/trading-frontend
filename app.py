from flask import Flask, jsonify
from flask_cors import CORS  # Import CORS
from pymongo import MongoClient
import yfinance as yf
import os

app = Flask(__name__)
CORS(app) # Enable CORS for all routes - this is important for local development

# MongoDB Connection URI from environment variable
mongo_uri = os.environ.get('MONGODB_URI')

if not mongo_uri:
    print("Error: MONGODB_URI environment variable not set.")
    exit(1)

client = MongoClient(mongo_uri)
db = client['trading']  # Database name is 'trading' as per your rules

def get_stock_prices(symbols):
    """Helper function to get real-time prices for multiple symbols"""
    prices = {}
    if symbols:
        try:
            tickers = yf.Tickers(' '.join(symbols))
            for symbol in symbols:
                try:
                    ticker = tickers.tickers[symbol]
                    info = ticker.fast_info
                    
                    # Get price data with fallback logic
                    current_price = getattr(info, 'last_price', None)
                    previous_close = getattr(info, 'previous_close', None)
                    
                    # Determine if market is closed (price is 0 or None)
                    is_market_closed = current_price is None or current_price == 0
                    
                    # Use previous close if market is closed or current price is invalid
                    price = previous_close if is_market_closed else current_price
                    
                    # Calculate change only if market is open
                    if not is_market_closed and previous_close:
                        change = current_price - previous_close
                        change_percent = (change / previous_close) * 100
                    else:
                        change = 0
                        change_percent = 0
                    
                    prices[symbol] = {
                        'price': price if price is not None else 0,
                        'change': change,
                        'changePercent': change_percent,
                        'previousClose': previous_close if previous_close is not None else 0,
                        'isMarketClosed': is_market_closed
                    }
                    
                    print(f"Fetched {symbol}: Price={price}, PrevClose={previous_close}, Market Closed={is_market_closed}")
                    
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
            # Get current holdings from summary
            portfolio = summary_data.get('portfolio', {})
            
            # Get purchase prices from trades collection
            purchase_prices = {}
            for symbol in portfolio.keys():
                # Get the latest BUY trade for each symbol
                last_buy = db.trades.find_one(
                    {'ticker': symbol, 'action': 'BUY'},
                    {'price': 1},
                    sort=[('timestamp', -1)]  # Get most recent
                )
                if last_buy:
                    purchase_prices[symbol] = last_buy['price']
            
            # Get real-time prices for holdings
            prices = get_stock_prices(portfolio.keys())
            
            # Calculate current portfolio value and details
            total_value = 0
            total_cost_basis = 0
            holdings_with_value = {}
            
            for symbol, shares in portfolio.items():
                current_price = prices.get(symbol, {}).get('price', 0)
                purchase_price = purchase_prices.get(symbol, 0)
                
                # Calculate values
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
                    'pl_percentage': pl_percentage,
                    'change': prices.get(symbol, {}).get('change', 0),
                    'changePercent': prices.get(symbol, {}).get('changePercent', 0)
                }
            
            # Update summary with real-time data
            summary_data['portfolio_details'] = holdings_with_value
            summary_data['total_portfolio_value'] = total_value
            summary_data['total_cost_basis'] = total_cost_basis
            summary_data['total_unrealized_pl'] = total_value - total_cost_basis
            summary_data['total_pl_percentage'] = ((total_value - total_cost_basis) / total_cost_basis * 100) if total_cost_basis > 0 else 0
            
            return jsonify(summary=summary_data)
        else:
            return jsonify(error="Summary data not found"), 404
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