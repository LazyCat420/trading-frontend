from flask import Flask, jsonify
from flask_cors import CORS  # Import CORS
from pymongo import MongoClient
import yfinance as yf
import os
from datetime import datetime, timedelta
from bson.decimal128 import Decimal128
from decimal import Decimal
from bson import ObjectId
import json

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

# Add this JSONEncoder class to handle MongoDB types
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, Decimal128):
            return float(obj.to_decimal())
        return super().default(obj)

# Update the Flask app config to use the custom encoder
app.json_encoder = MongoJSONEncoder

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

# Add this helper function at the top with other imports
def convert_mongodb_types(data):
    """Recursively convert MongoDB types to Python native types"""
    if isinstance(data, dict):
        return {key: convert_mongodb_types(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_mongodb_types(item) for item in data]
    elif isinstance(data, Decimal128):
        return float(data.to_decimal())
    elif isinstance(data, ObjectId):
        return str(data)
    return data

@app.route('/trades')
def get_trades():
    try:
        # Get trades and exclude _id field
        trades = list(db.trades.find({}, {'_id': 0}))
        
        # Convert all MongoDB types to Python native types
        trades = convert_mongodb_types(trades)
        
        return jsonify({'trades': trades})
    except Exception as e:
        print(f"Error in trades: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
        latest_data = db.summary.find_one({}, {'_id': 0})
        print("Raw MongoDB data:", latest_data)
        
        if not latest_data:
            return jsonify({'error': 'No summary data found'}), 404

        latest_data = convert_mongodb_types(latest_data)
        
        portfolio = latest_data.get('portfolio', {})
        balance = float(latest_data.get('balance', 0))
        
        positions = []
        portfolio_details = {}  # Create portfolio_details separately
        total_pl = 0
        total_value = 0
        
        for symbol, position in portfolio.items():
            if isinstance(position, dict):
                shares = float(position.get('shares', 0))
                current_price = float(position.get('current_price', 0))
                market_value = float(position.get('market_value', 0))
                buy_price = float(position.get('buy_price', current_price))
                
                # Calculate P/L
                pl = market_value - (shares * buy_price)
                pl_pct = ((current_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
                
                total_pl += pl
                total_value += market_value
                
                position_data = {
                    'symbol': symbol,
                    'shares': shares,
                    'purchase_price': buy_price,
                    'current_price': current_price,
                    'current_value': market_value,
                    'unrealized_pl': pl,
                    'pl_percentage': pl_pct
                }
                positions.append(position_data)
                
                # Add to portfolio_details
                portfolio_details[symbol] = {
                    'shares': shares,
                    'purchase_price': buy_price,
                    'current_price': current_price,
                    'current_value': market_value,
                    'unrealized_pl': pl,
                    'pl_percentage': pl_pct
                }
        
        # Calculate total portfolio metrics
        total_pl_percentage = (total_pl / (total_value - total_pl) * 100) if (total_value - total_pl) > 0 else 0
        
        summary_data = {
            'summary': {
                'holdings': positions,
                'total_portfolio_value': total_value,
                'cash_balance': balance,
                'total_value': total_value + balance,
                'total_unrealized_pl': total_pl,
                'total_pl_percentage': total_pl_percentage,
                'portfolio_details': portfolio_details  # Use the separately built portfolio_details
            }
        }
        
        print("Final summary data:", summary_data)
        return jsonify(summary_data)
        
    except Exception as e:
        print(f"Error in summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

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

# Add this helper function to convert Decimal128 to float
def convert_decimal128(obj):
    if isinstance(obj, Decimal128):
        return float(obj.to_decimal())
    return obj

if __name__ == '__main__':
    app.run(debug=True, port=5000) # Run Flask app on port 5000 