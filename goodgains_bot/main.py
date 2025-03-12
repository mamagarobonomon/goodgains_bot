import asyncio
import logging
from threading import Thread
import sys
import signal

# Import configuration
from config import DISCORD_BOT_TOKEN, NGROK_ENABLED, FLASK_PORT

# Import modules
from database.connection import initialize_database
from web.server import app, run_flask_server
from web.ngrok import setup_ngrok
from bot.bot import GoodGainsBot
from utils.logging import setup_logging

# Set up logging
logger = setup_logging()

# Initialize the bot
bot = GoodGainsBot()

# Make bot available to Flask app
from web.server import app

app.config['bot'] = bot


# Function to clean up resources on shutdown
def shutdown_handler(signum, frame):
    logger.info("Shutdown signal received, cleaning up...")
    # Any cleanup needed
    sys.exit(0)


def main():
    # Initialize database
    initialize_database()
    logger.info("Database initialized")

    # Register commands
    from commands import register_all_commands
    register_all_commands(bot)

    # Set up ngrok if enabled
    ngrok_url = None
    if NGROK_ENABLED:
        try:
            ngrok_url = setup_ngrok(FLASK_PORT)
        except Exception as e:
            logger.error(f"Failed to set up ngrok: {e}")
            print(f"Failed to set up ngrok: {e}")
            print("Continuing without ngrok...")

    # Start Flask server in a separate thread
    flask_thread = Thread(target=run_flask_server, args=(FLASK_PORT,))
    flask_thread.daemon = True
    flask_thread.start()
    logger.info(f"Flask server started on port {FLASK_PORT}")

    # Register shutdown handler
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Load caches from database
    bot.reload_caches()

    # Run the bot (this will block until the bot is stopped)
    logger.info("Starting Discord bot...")
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()