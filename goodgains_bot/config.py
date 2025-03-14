import os
import logging
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Load environment variables
load_dotenv()

# Discord Bot
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 0))

# API Keys
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
INFURA_URL = os.getenv("INFURA_NODE_URL")
WALLETCONNECT_PROJECT_ID = os.getenv("WALLET_CONNECT_PROJECT_ID")

# Smart Contract
CONTRACT_ADDRESS = os.getenv("SMART_CONTRACT_ADDRESS")

# Ngrok
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")
NGROK_ENABLED = os.getenv("NGROK_ENABLED", "true").lower() == "true"

# Encryption for wallet private key
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
ENCRYPTED_WALLET_PRIVATE_KEY = os.getenv("ENCRYPTED_WALLET_PRIVATE_KEY")

# Betting settings
COMMISSION_RATE = float(os.getenv("COMMISSION_RATE", "0.15"))
MAX_BET_AMOUNT = float(os.getenv("MAX_BET_AMOUNT", "1.0"))
MIN_BET_AMOUNT = float(os.getenv("MIN_BET_AMOUNT", "0.01"))
API_RATE_LIMIT = int(os.getenv("API_RATE_LIMIT", "30"))
MAX_BETS_PER_HOUR = int(os.getenv("MAX_BETS_PER_HOUR", "5"))

# Database
DB_PATH = "goodgains.db"

# Web server
FLASK_PORT = 8081

# Initialize encryption
if ENCRYPTION_KEY:
    fernet = Fernet(ENCRYPTION_KEY)
else:
    logging.error("ENCRYPTION_KEY not found in .env")
    fernet = None


# Match detection settings
MATCH_DETECTION_POLL_INTERVAL = int(os.getenv("MATCH_DETECTION_POLL_INTERVAL", "15"))
MATCH_DETECTION_CONFIDENCE_THRESHOLD = int(os.getenv("MATCH_DETECTION_CONFIDENCE", "80"))
MATCH_API_PRIORITY = os.getenv("MATCH_API_PRIORITY", "high").lower()
