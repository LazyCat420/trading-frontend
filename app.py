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
            # Fetch all prices in one batch
            tickers = yf.Tickers(' '.join(symbols))
            for symbol in symbols:
                try:
                    ticker = tickers.tickers[symbol]
                    info = ticker.fast_info  # Use fast_info instead of info for better performance
                    
                    current_price = info.last_price if hasattr(info, 'last_price') else info.get('regularMarketPrice', 0)
                    previous_close = info.previous_close if hasattr(info, 'previous_close') else info.get('previousClose', 0)
                    
                    # If current price is not available, use previous close
                    price = current_price if current_price and current_price > 0 else previous_close
                    
                    prices[symbol] = {
                        'price': price,
                        'change': 0,  # Set to 0 when market is closed
                        'changePercent': 0,  # Set to 0 when market is closed
                        'previousClose': previous_close,
                        'isMarketClosed': True
                    }
                    
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
        # First, get the watchlist data from MongoDB
        watchlist_data = list(db.watchlist.find({}, {'_id': 0}))
        
        if watchlist_data and 'sector_watchlists' in watchlist_data[0]:
            sectors = watchlist_data[0]['sector_watchlists']
            
            # Extract all symbols from the MongoDB data while maintaining sector organization
            all_symbols = []
            for sector, stocks in sectors.items():
                # Ensure stocks is a list and contains valid symbols
                if isinstance(stocks, list):
                    # Add each stock symbol to our list if it's not already there
                    all_symbols.extend([stock for stock in stocks if stock and isinstance(stock, str)])
            
            # Remove duplicates while preserving order
            all_symbols = list(dict.fromkeys(all_symbols))
            
            if all_symbols:  # Only proceed if we have symbols to look up
                try:
                    print(f"Fetching prices for symbols: {all_symbols}")  # Debug log
                    # Create a single Tickers object for all symbols
                    tickers = yf.Tickers(' '.join(all_symbols))
                    prices = {}
                    
                    for symbol in all_symbols:
                        try:
                            ticker = tickers.tickers[symbol]
                            info = ticker.info
                            
                            # Get the price data
                            current_price = info.get('regularMarketPrice')
                            previous_close = info.get('previousClose')
                            
                            if current_price is not None and previous_close is not None:
                                change = current_price - previous_close
                                change_percent = (change / previous_close) * 100
                            else:
                                change = info.get('regularMarketChange', 0)
                                change_percent = info.get('regularMarketChangePercent', 0)
                            
                            prices[symbol] = {
                                'price': current_price if current_price is not None else 0,
                                'change': change if change is not None else 0,
                                'changePercent': change_percent if change_percent is not None else 0,
                                'previousClose': previous_close if previous_close is not None else 0
                            }
                            print(f"Successfully fetched price for {symbol}: {prices[symbol]}")  # Debug log
                            
                        except Exception as e:
                            print(f"Error fetching data for {symbol}: {str(e)}")
                            prices[symbol] = {
                                'price': 0,
                                'change': 0,
                                'changePercent': 0,
                                'previousClose': 0
                            }
                    
                    # Add the prices to the watchlist data
                    watchlist_data[0]['prices'] = prices
                    
                except Exception as e:
                    print(f"Error in batch price fetch: {str(e)}")
                    # Provide empty prices if batch fetch fails
                    watchlist_data[0]['prices'] = {symbol: {
                        'price': 0,
                        'change': 0,
                        'changePercent': 0,
                        'previousClose': 0
                    } for symbol in all_symbols}
            
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