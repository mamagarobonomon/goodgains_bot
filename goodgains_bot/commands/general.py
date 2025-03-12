import discord
from discord import app_commands
import logging
from io import BytesIO
import json
from api.steam import extract_steam_id_from_url, resolve_vanity_url
from database.connection import get_db_connection
from gsi.parser import generate_gsi_config
from config import NGROK_ENABLED

logger = logging.getLogger('goodgains_bot')


def register_commands(bot):
    """Register general utility commands."""

    @bot.tree.command(name="help", description="Get help with GoodGains bot commands")
    @app_commands.describe(command="Optional: Get detailed help on a specific command")
    async def help_command(interaction: discord.Interaction, command: str = None):
        """Show help information for the bot commands."""
        if command:
            # Detailed help for specific command
            command = command.lower()

            if command == "link_steam":
                await interaction.response.send_message(
                    "**`/link_steam` Command**\n\n"
                    "Links your Discord account to your Steam account for game detection.\n\n"
                    "**Usage:** `/link_steam steam_url`\n\n"
                    "**Example:** `/link_steam https://steamcommunity.com/id/username`\n\n"
                    "Your Steam profile must be public for game detection to work."
                )

            elif command == "connect_wallet":
                await interaction.response.send_message(
                    "**`/connect_wallet` Command**\n\n"
                    "Connects your Ethereum wallet using WalletConnect.\n\n"
                    "**Usage:** `/connect_wallet`\n\n"
                    "You'll receive a QR code to scan with your wallet app. This connection is required for placing bets."
                )

            elif command == "bet":
                await interaction.response.send_message(
                    "**`/bet` Command**\n\n"
                    "Place a bet on your team winning the current match.\n\n"
                    "**Usage:** `/bet amount`\n\n"
                    "**Example:** `/bet 0.1`\n\n"
                    "This will bet 0.1 ETH on your team winning. Only available in the first 5 minutes of a match."
                )

            elif command == "profile":
                await interaction.response.send_message(
                    "**`/profile` Command**\n\n"
                    "View your betting profile and history.\n\n"
                    "**Usage:** `/profile [private]`\n\n"
                    "Set `private` to `True` to show your profile only to yourself."
                )

            elif command == "check_match":
                await interaction.response.send_message(
                    "**`/check_match` Command**\n\n"
                    "Manually check if you're in an active Dota 2 match.\n\n"
                    "**Usage:** `/check_match`\n\n"
                    "Use this if you think the bot hasn't detected your game automatically."
                )

            else:
                await interaction.response.send_message(f"No detailed help available for '{command}'.")

        else:
            # General help
            await interaction.response.send_message(
                "**GoodGains Bot Help**\n\n"
                "**Getting Started:**\n"
                "1️⃣ `/link_steam` - Link your Steam account\n"
                "2️⃣ `/connect_wallet` - Connect your Ethereum wallet\n"
                "3️⃣ Play Dota 2 and place bets!\n\n"

                "**Main Commands:**\n"
                "• `/bet [amount]` - Bet on your team winning\n"
                "• `/bet_first_blood [player] [amount]` - Bet on First Blood\n"
                "• `/bet_mvp [player] [amount]` - Bet on MVP\n"
                "• `/profile` - View your betting stats\n"
                "• `/check_match` - Check if you're in a match\n\n"

                "**Wallet Commands:**\n"
                "• `/wallet_status` - Check wallet connection\n"
                "• `/disconnect_wallet` - Disconnect wallet\n\n"

                "For more details on any command, use `/help [command]`"
            )

    @bot.tree.command(name="link_steam", description="Link your Steam account using your profile URL")
    @app_commands.describe(steam_url="Your Steam profile URL (e.g., https://steamcommunity.com/id/username)")
    async def link_steam(interaction: discord.Interaction, steam_url: str):
        """Link a Steam account using a profile URL."""
        user_id = interaction.user.id

        # Validate URL format
        steam_id_or_vanity = extract_steam_id_from_url(steam_url)
        if not steam_id_or_vanity:
            await interaction.response.send_message(
                "❌ Please provide a valid Steam profile URL (e.g., https://steamcommunity.com/id/username).",
                ephemeral=True
            )
            return

        # If it's a vanity URL, resolve it to a Steam ID
        steam_id = steam_id_or_vanity
        if not steam_id.isdigit() or len(steam_id) != 17:
            # Not a valid Steam ID, try to resolve vanity URL
            steam_id = await resolve_vanity_url(steam_id_or_vanity)
            if not steam_id:
                await interaction.response.send_message(
                    "❌ Could not resolve this vanity URL. Please use your Steam profile URL with ID.",
                    ephemeral=True
                )
                return

        # Save to database
        with get_db_connection() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO steam_mappings (user_id, steam_id) VALUES (?, ?)',
                (user_id, steam_id)
            )
            conn.commit()

        # Update cache
        bot.steam_ids_cache[user_id] = steam_id

        logger.info(f"Linked Discord user {user_id} to Steam ID {steam_id}")

        # Generate GSI config file
        endpoint_url = bot.ngrok_url if hasattr(bot, 'ngrok_url') and bot.ngrok_url else f"http://your-server:8081"
        config_content = generate_gsi_config(user_id, endpoint_url)

        # Create file and send instructions
        buffer = BytesIO(config_content.encode())
        buffer.seek(0)

        # Create a discord.File object from the buffer
        config_file = discord.File(buffer, filename="gamestate_integration_goodgains.cfg")

        # Create installation instructions
        instructions = (
            f"# Steam ID linked successfully: {steam_id}\n\n"
            f"# GoodGains In-Game Betting Setup\n\n"
            f"Follow these steps to enable in-game betting:\n\n"
            f"1. Save the attached file to your Dota 2 game folder at:\n"
            f"   `[Steam Location]/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/`\n\n"
            f"2. Create the 'gamestate_integration' folder if it doesn't exist\n\n"
            f"3. Restart Dota 2 completely\n\n"
            f"4. In-game commands will now work:\n"
            f"   - `!bet 0.1 team` - Bet on your team winning\n"
            f"   - `!bet 0.1 fb PlayerName` - Bet on First Blood\n"
            f"   - `!bet 0.1 mvp PlayerName` - Bet on MVP\n"
            f"   - `!balance` - Check your balance\n"
            f"   - `!help` - Show help\n\n"
            f"Note: All bets are in testing mode, no real crypto is used."
        )

        # Send the response
        await interaction.response.send_message(
            instructions,
            file=config_file,
            ephemeral=False
        )

    @bot.tree.command(name="check_match", description="Manually check if you're in an active match")
    async def check_match(interaction: discord.Interaction):
        """Manually trigger match detection for the user."""
        user_id = interaction.user.id

        await interaction.response.defer(ephemeral=True)

        # Check if user has linked Steam ID
        if user_id not in bot.steam_ids_cache:
            await interaction.followup.send("❌ You need to link your Steam ID first with `/link_steam <url>`")
            return

        steam_id = bot.steam_ids_cache[user_id]
        logger.info(f"Manual match check requested by user {user_id} with Steam ID {steam_id}")

        # Import the check_dota2_match function from tasks
        from bot.tasks import check_dota2_match

        # Force check for Dota 2 match
        is_in_match = await check_dota2_match(bot, user_id, steam_id)

        if is_in_match:
            # If match found, the update_player_match would have sent notification already
            await interaction.followup.send(
                "✅ Found you in an active Dota 2 match! Check the notification channel."
            )
        else:
            await interaction.followup.send(
                "❌ Could not find you in an active Dota 2 match. Are you currently in a game?"
            )

    @bot.tree.command(name="clear_match", description="Clear your active match status if stuck")
    async def clear_match(interaction: discord.Interaction):
        """Clear the user's active match status if the bot thinks they're still in a game."""
        user_id = interaction.user.id

        await interaction.response.defer(ephemeral=True)

        with get_db_connection() as conn:
            # Get current active match info before deletion
            match_info = conn.execute(
                'SELECT match_id, team FROM active_players WHERE user_id = ?',
                (user_id,)
            ).fetchone()

            # Delete from database
            deleted = conn.execute(
                'DELETE FROM active_players WHERE user_id = ?',
                (user_id,)
            ).rowcount > 0
            conn.commit()

        # Also clear from cache
        from bot.bot import active_players_lock
        was_in_cache = False
        match_id_cache = None

        with active_players_lock:
            if user_id in bot.active_players_cache:
                match_id_cache = bot.active_players_cache[user_id].get('match_id')
                was_in_cache = True
                del bot.active_players_cache[user_id]

        if deleted or was_in_cache:
            match_id = match_info['match_id'] if match_info else (match_id_cache if was_in_cache else "unknown")
            logger.info(f"Manually cleared user {user_id} from match {match_id}")
            await interaction.followup.send(
                f"✅ Successfully cleared your status from match {match_id}. You can now be detected in new matches."
            )

            # Also send to log channel
            try:
                await bot.get_channel(bot.log_channel_id).send(
                    f"🔄 <@{user_id}> has been manually cleared from match {match_id}."
                )
            except Exception as e:
                logger.error(f"Failed to send log channel notification: {e}")
        else:
            await interaction.followup.send("✅ You were not currently in any active match.")

    @bot.tree.command(name="setup_ingame", description="Generate Game State Integration config for in-game betting")
    async def setup_ingame(interaction: discord.Interaction):
        """Generate a GSI config file for Dota 2 in-game betting."""
        user_id = interaction.user.id

        # Check if user has linked Steam ID
        if user_id not in bot.steam_ids_cache:
            await interaction.response.send_message(
                "❌ You need to link your Steam ID first with `/link_steam <url>`",
                ephemeral=True
            )
            return

        # Generate GSI config
        endpoint_url = bot.ngrok_url if hasattr(bot, 'ngrok_url') and bot.ngrok_url else f"http://your-server:8081"
        config_content = generate_gsi_config(user_id, endpoint_url)

        # Create file and send instructions
        buffer = BytesIO(config_content.encode())
        buffer.seek(0)

        # Create a discord.File object from the buffer
        config_file = discord.File(buffer, filename="gamestate_integration_goodgains.cfg")

        # Create installation instructions
        instructions = (
            f"# GoodGains In-Game Betting Setup\n\n"
            f"Follow these steps to enable in-game betting:\n\n"
            f"1. Save the attached file to your Dota 2 game folder at:\n"
            f"   `[Steam Location]/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/`\n\n"
            f"2. Create the 'gamestate_integration' folder if it doesn't exist\n\n"
            f"3. Restart Dota 2 completely\n\n"
            f"4. In-game commands will now work:\n"
            f"   - `!bet 0.1 team` - Bet on your team winning\n"
            f"   - `!bet 0.1 fb PlayerName` - Bet on First Blood\n"
            f"   - `!bet 0.1 mvp PlayerName` - Bet on MVP\n"
            f"   - `!balance` - Check your balance\n"
            f"   - `!help` - Show help\n\n"
            f"Note: All bets are in testing mode, no real crypto is used."
        )

        # Send both the file and instructions
        await interaction.response.send_message(
            instructions,
            file=config_file,
            ephemeral=True
        )

        logger.info(f"Sent GSI config to user {user_id}")

    logger.info("General commands registered")
    return bot