from flask import Flask, request, jsonify
import logging
import asyncio
import json
from datetime import datetime
from database.connection import get_db_connection
from gsi.handlers import process_dota2_gsi_data

logger = logging.getLogger('goodgains_bot')

app = Flask(__name__)
bot = None  # Will be set by main.py


@app.route('/')
def index():
    return "GoodGains Bot API is running!"


@app.route('/webhook/walletconnect', methods=['POST'])
def wallet_connect_webhook():
    """Handle WalletConnect webhook callbacks."""
    try:
        logger.info(f"Received WalletConnect webhook at {request.path}")
        data = request.get_json()
        logger.info(f"Webhook data: {data}")

        # Extract topic (session_id) and address from request
        topic = data.get('topic') or data.get('session_id')
        wallet_address = data.get('address') or data.get('accounts', [None])[0]

        if not topic or not wallet_address:
            logger.warning(f"Invalid webhook data: {data}")
            return {'status': 'error', 'message': 'Invalid webhook data'}, 400

        # Find user by session ID
        with get_db_connection() as conn:
            user_row = conn.execute(
                'SELECT user_id FROM wallet_sessions WHERE session_id = ?',
                (topic,)
            ).fetchone()

            if not user_row:
                logger.warning(f"Session not found for topic: {topic}")
                return {'status': 'error', 'message': 'Session not found'}, 404

            user_id = user_row['user_id']

            # Update session with wallet address
            conn.execute(
                'UPDATE wallet_sessions SET wallet_address = ?, connected = TRUE, last_active = ? WHERE session_id = ?',
                (wallet_address, datetime.now().isoformat(), topic)
            )
            conn.commit()
            logger.info(f"User {user_id} connected wallet {wallet_address}")

        return {'status': 'success'}, 200
    except Exception as e:
        logger.error(f"Error in WalletConnect webhook: {e}")
        return {'status': 'error', 'message': str(e)}, 500


@app.route('/gsi/dota2', methods=['POST'])
def dota2_gsi_endpoint():
    """Handle Dota 2 Game State Integration data."""
    try:
        logger.info(f"Received GSI data: {request.headers}")
        logger.info(f"Request data sample: {str(request.data)[:100]}")

        data = request.get_json()
        user_id = None

        # Extract auth token to identify the user
        if 'auth' in data and 'token' in data['auth']:
            auth_token = data['auth']['token']

            # Format: discord{user_id}
            if auth_token.startswith('discord'):
                try:
                    user_id = int(auth_token[7:])  # Remove 'discord' prefix

                    # Log the GSI connection
                    with get_db_connection() as conn:
                        conn.execute(
                            'INSERT INTO gsi_connections (user_id, timestamp) VALUES (?, ?)',
                            (user_id, datetime.now().isoformat())
                        )
                        conn.commit()
                except Exception as e:
                    logger.error(f"Error processing GSI auth token: {e}")

        # Process the GSI data
        process_dota2_gsi_data(data, user_id, bot)

        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error in GSI endpoint: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def run_flask_server(port=8081):
    """Run the Flask server."""
    app.run(host='0.0.0.0', port=port)