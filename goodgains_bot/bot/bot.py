import discord
from discord.ext import commands
import logging
import asyncio
from threading import Lock
from datetime import datetime
from config import DISCORD_BOT_TOKEN, LOG_CHANNEL_ID
from database.connection import get_db_connection
from api.rate_limiter import ApiRateLimiter

logger = logging.getLogger('goodgains_bot')

# Locks for thread safety
active_players_lock = Lock()
bets_lock = Lock()
sessions_lock = Lock()


class GoodGainsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix="/", intents=intents)

        # Initialize in-memory caches
        self.steam_ids_cache = {}
        self.active_players_cache = {}
        self.wallet_sessions_cache = {}
        self.user_status_cache = {}
        self.user_game_cache = {}
        self.completed_matches = set()
        self.recently_cleaned_matches = {}
        self.potential_match_start = {}
        self.game_state_cache = {}  # Track game state transitions
        self.match_detection_confidence = {}  # Track confidence levels of match detection

        # Initialize API rate limiter
        self.api_limiter = ApiRateLimiter()

        # Start time for uptime calculation
        self.start_time = datetime.now()

    def reload_caches(self):
        """Load data from database into memory caches."""
        self.steam_ids_cache = {}
        self.active_players_cache = {}
        self.wallet_sessions_cache = {}

        with get_db_connection() as conn:
            # Load Steam IDs
            for row in conn.execute('SELECT user_id, steam_id FROM steam_mappings'):
                self.steam_ids_cache[row['user_id']] = row['steam_id']

            # Load active players
            for row in conn.execute('SELECT user_id, game_id, match_id, team, match_start_time FROM active_players'):
                self.active_players_cache[row['user_id']] = {
                    'game_id': row['game_id'],
                    'match_id': row['match_id'],
                    'team': row['team'],
                    'match_start_time': row['match_start_time'],
                    'last_check_time': int(datetime.now().timestamp())
                }

            # Load wallet sessions
            for row in conn.execute(
                    'SELECT user_id, wallet_address, session_id, connected FROM wallet_sessions WHERE connected = TRUE'):
                self.wallet_sessions_cache[row['user_id']] = {
                    'address': row['wallet_address'],
                    'session_id': row['session_id'],
                    'connected': row['connected']
                }

    async def on_ready(self):
        logger.info(f'Logged in as {self.user.name} (ID: {self.user.id})')
        logger.info('------')

        # Sync slash commands with Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def setup_hook(self):
        """Register background tasks."""
        # Import tasks here to avoid circular imports
        from bot.tasks import start_tasks
        start_tasks(self)

    def get_uptime(self):
        """Return the bot's uptime in a human-readable format."""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()

        # Convert to days, hours, minutes, seconds
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        return f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"

    async def send_direct_message(self, user_id, message):
        """Send a direct message to a user safely."""
        try:
            user = await self.fetch_user(user_id)
            if user:
                await user.send(message)
                logger.info(f"DM sent to user {user_id}")
            else:
                logger.warning(f"Could not find user with ID {user_id}")
        except discord.Forbidden:
            logger.warning(f"Cannot send DM to user {user_id} (forbidden)")
        except Exception as e:
            logger.error(f"Error sending DM to user {user_id}: {e}")