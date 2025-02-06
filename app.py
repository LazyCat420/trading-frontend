from flask import Flask, jsonify
from flask_cors import CORS  # Import CORS
from pymongo import MongoClient
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

@app.route('/watchlist')
def get_watchlist():
    print("Request received for /watchlist") # Debug log
    watchlist_data = list(db.watchlist.find({}, {'_id': 0})) # Fetch watchlist data, exclude _id
    print(f"Watchlist data fetched: {watchlist_data}") # Debug log
    return jsonify(watchlist=watchlist_data)

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
    print("Request received for /summary") # Debug log
    summary_data = db.summary.find_one({}, {'_id': 0})
    print(f"Summary data fetched: {summary_data}") # Debug log
    if summary_data:
        return jsonify(summary=summary_data)
    else:
        return jsonify(error="Summary data not found"), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000) # Run Flask app on port 5000 