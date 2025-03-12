import logging
from pyngrok import ngrok, conf
from config import NGROK_AUTH_TOKEN

logger = logging.getLogger('goodgains_bot')

def setup_ngrok(port=8081):
    """Set up an ngrok tunnel to expose the Flask app."""
    if not NGROK_AUTH_TOKEN:
        logger.warning("No NGROK_AUTH_TOKEN provided, ngrok may have limitations")
    else:
        conf.get_default().auth_token = NGROK_AUTH_TOKEN

    try:
        # Connect to ngrok
        public_url = ngrok.connect(port).public_url
        logger.info(f"Flask app exposed via ngrok: {public_url}")

        # Display info in console
        print("\n" + "=" * 80)
        print(f"NGROK TUNNEL ACTIVE: {public_url}")
        print(f"WalletConnect Webhook URL: {public_url}/webhook/walletconnect")
        print(f"Dota 2 GSI Endpoint: {public_url}/gsi/dota2")
        print("=" * 80 + "\n")

        return public_url
    except Exception as e:
        logger.error(f"Failed to set up ngrok: {e}")
        return None