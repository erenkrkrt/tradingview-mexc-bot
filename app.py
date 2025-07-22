# TradingView to MEXC Trading Bot
import os
import json
import hashlib
import hmac
import time
import requests
from flask import Flask, request, jsonify
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# MEXC API Configuration
MEXC_API_KEY = os.environ.get('MEXC_API_KEY')
MEXC_SECRET_KEY = os.environ.get('MEXC_SECRET_KEY')
MEXC_BASE_URL = "https://api.mexc.com"

class MEXCTrader:
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = MEXC_BASE_URL

    def _generate_signature(self, params, timestamp):
        """MEXC için signature oluştur"""
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        query_string += f"&timestamp={timestamp}"
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _send_request(self, method, endpoint, params=None):
        """MEXC API'ye request gönder"""
        if params is None:
            params = {}
        
        timestamp = str(int(time.time() * 1000))
        params['timestamp'] = timestamp
        
        headers = {
            'X-MEXC-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        
        signature = self._generate_signature(params, timestamp)
        params['signature'] = signature
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'GET':
                response = requests.get(url, params=params, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=params, headers=headers)
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"MEXC API Error: {e}")
            return None

    def place_order(self, symbol, side, quantity, order_type='MARKET'):
        """Emir ver"""
        params = {
            'symbol': symbol,
            'side': side,  # BUY veya SELL
            'type': order_type,
            'quoteOrderQty': str(quantity)  # USDT cinsinden miktar
        }
        
        return self._send_request('POST', '/api/v3/order', params)

    def get_account_info(self):
        """Hesap bilgilerini al"""
        return self._send_request('GET', '/api/v3/account')

    def cancel_all_orders(self, symbol):
        """Tüm açık emirleri iptal et"""
        return self._send_request('DELETE', '/api/v3/openOrders', {'symbol': symbol})

# Global trader instance
trader = None

def initialize_trader():
    global trader
    if MEXC_API_KEY and MEXC_SECRET_KEY:
        trader = MEXCTrader(MEXC_API_KEY, MEXC_SECRET_KEY)
        logging.info("MEXC Trader initialized")
        return True
    else:
        logging.error("MEXC API credentials not found!")
        return False

@app.route('/')
def home():
    """Ana sayfa"""
    return jsonify({
        'status': 'TradingView MEXC Bot Running',
        'version': '1.0',
        'endpoints': {
            'webhook': '/webhook',
            'status': '/status',
            'test': '/test'
        }
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView webhook endpoint"""
    try:
        data = request.get_json()
        logging.info(f"Received webhook: {data}")
        
        if not trader:
            initialize_trader()
            if not trader:
                return jsonify({'error': 'MEXC trader not initialized'}), 500
        
        # TradingView'den gelen mesaj formatı:
        # {
        #   "action": "buy" | "sell" | "close_long" | "close_short",
        #   "symbol": "BTCUSDT",
        #   "quantity": 50  # USDT cinsinden
        # }
        
        action = data.get('action')
        symbol = data.get('symbol', 'BTCUSDT')
        quantity = data.get('quantity', 10)  # Default 10 USDT
        
        if action in ['buy', 'long']:
            # Long pozisyon aç
            result = trader.place_order(symbol, 'BUY', quantity, 'MARKET')
            message = f"LONG açıldı: {symbol} - {quantity} USDT"
            
        elif action in ['sell', 'short']:
            # Short pozisyon aç (Spot'ta sell için önce coin sahibi olman gerekir)
            result = trader.place_order(symbol, 'SELL', quantity, 'MARKET')
            message = f"SELL açıldı: {symbol} - {quantity} USDT"
            
        elif action in ['close_long', 'close_short', 'close']:
            # Pozisyonu kapat (açık emirleri iptal et)
            result = trader.cancel_all_orders(symbol)
            message = f"Pozisyon kapatıldı: {symbol}"
            
        else:
            return jsonify({'error': 'Invalid action'}), 400
        
        if result:
            logging.info(f"Trade executed: {message}")
            return jsonify({
                'status': 'success',
                'message': message,
                'mexc_response': result
            })
        else:
            return jsonify({'error': 'Trade failed'}), 500
            
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    """Bot durumunu kontrol et"""
    if not trader:
        initialize_trader()
    
    if not trader:
        return jsonify({'status': 'error', 'message': 'Trader not initialized'})
    
    # Hesap bilgilerini al
    account_info = trader.get_account_info()
    
    return jsonify({
        'status': 'running',
        'mexc_connected': account_info is not None,
        'timestamp': int(time.time()),
        'api_key_configured': MEXC_API_KEY is not None,
        'secret_key_configured': MEXC_SECRET_KEY is not None
    })

@app.route('/test', methods=['POST'])
def test_trade():
    """Test işlemi"""
    if not trader:
        initialize_trader()
        if not trader:
            return jsonify({'error': 'Trader not initialized'}), 500
    
    try:
        # Test için hesap bilgilerini al
        account_info = trader.get_account_info()
        
        if account_info:
            return jsonify({
                'status': 'success',
                'message': 'MEXC bağlantısı başarılı!',
                'account_info': account_info
            })
        else:
            return jsonify({'error': 'MEXC bağlantısı başarısız!'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    initialize_trader()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
