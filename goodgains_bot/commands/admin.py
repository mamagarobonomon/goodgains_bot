import discord
from discord import app_commands
import logging
import psutil
from datetime import datetime
from database.connection import get_db_connection
from bot.bot import active_players_lock

logger = logging.getLogger('goodgains_bot')


def register_commands(bot):
    """Register admin-only commands."""

    @bot.tree.command(name="bot_status", description="Check the health of the bot (admin only)")
    async def bot_status(interaction: discord.Interaction):
        """Get detailed status information about the bot."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ This command is for administrators only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Gather statistics
        with get_db_connection() as conn:
            active_matches = conn.execute('SELECT COUNT(*) as count FROM active_players').fetchone()['count']
            pending_bets = conn.execute('SELECT COUNT(*) as count FROM bets WHERE resolved = FALSE').fetchone()['count']
            user_count = conn.execute('SELECT COUNT(DISTINCT user_id) as count FROM steam_mappings').fetchone()['count']
            wallet_count = \
            conn.execute('SELECT COUNT(*) as count FROM wallet_sessions WHERE connected = TRUE').fetchone()['count']

        # Check API status
        from api.steam import check_api_health
        steam_api_status = "✅ Working" if await check_api_health() else "⚠️ Issues detected"

        # Memory usage
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024  # MB

        # Format response
        status_message = (
            "🤖 **Bot Status**\n\n"
            f"**Active Matches:** {active_matches}\n"
            f"**Pending Bets:** {pending_bets}\n"
            f"**Registered Users:** {user_count}\n"
            f"**Connected Wallets:** {wallet_count}\n\n"
            f"**Steam API:** {steam_api_status}\n"
            f"**Memory Usage:** {memory_usage:.2f} MB\n"
            f"**Uptime:** {bot.get_uptime()}\n"
            f"**API Rate Limits:** {len(bot.api_limiter.failures)} failures tracked\n"
        )

        await interaction.followup.send(status_message)

    @bot.tree.command(name="clean_synthetic_matches", description="Admin-only: Clean up legacy synthetic matches")
    async def clean_synthetic_matches(interaction: discord.Interaction):
        """Remove all synthetic matches from the database."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ This command is for administrators only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        with get_db_connection() as conn:
            # Find all synthetic matches
            synthetic_matches = conn.execute(
                "SELECT match_id FROM active_players WHERE match_id LIKE 'dota_%' OR match_id LIKE 'sim_%'"
            ).fetchall()

            if not synthetic_matches:
                await interaction.followup.send("✅ No synthetic matches found in the database.")
                return

            match_count = len(synthetic_matches)
            match_ids = [match['match_id'] for match in synthetic_matches]

            # Remove from active_players
            conn.execute(
                "DELETE FROM active_players WHERE match_id LIKE 'dota_%' OR match_id LIKE 'sim_%'"
            )

            # Find unresolved bets on synthetic matches
            unresolved_bets = conn.execute(
                "SELECT COUNT(*) as count FROM bets WHERE (match_id LIKE 'dota_%' OR match_id LIKE 'sim_%') AND resolved = FALSE"
            ).fetchone()

            # Mark all bets on synthetic matches as resolved with no winner
            conn.execute(
                "UPDATE bets SET resolved = TRUE, won = FALSE, payout = 0 WHERE match_id LIKE 'dota_%' OR match_id LIKE 'sim_%'"
            )

            conn.commit()

        await interaction.followup.send(
            f"✅ Cleaned up {match_count} synthetic matches:\n" +
            "\n".join(match_ids[:10]) +  # Show first 10
            (f"\n...and {match_count - 10} more" if match_count > 10 else "") +
            f"\n\nMarked {unresolved_bets['count']} unresolved bets as losses."
        )

        # Also clear cache
        with active_players_lock:
            for user_id in list(bot.active_players_cache.keys()):
                match_id = bot.active_players_cache[user_id]['match_id']
                if match_id.startswith('dota_') or match_id.startswith('sim_'):
                    del bot.active_players_cache[user_id]

        logger.info(f"Admin {interaction.user.id} cleaned up {match_count} synthetic matches")

    @bot.tree.command(name="record_event", description="Record a match event (testing only)")
    @app_commands.describe(
        match_id="The match ID",
        event_type="Type of event (first_blood, mvp, etc.)",
        target="Target of the event (player name, etc.)"
    )
    async def record_event(interaction: discord.Interaction, match_id: str, event_type: str, target: str):
        """Record a match event for testing event-based bets."""
        # Admin-only check
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ This command is for administrators only.", ephemeral=True)
            return

        with get_db_connection() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO match_events (match_id, event_type, event_target, event_time) VALUES (?, ?, ?, ?)',
                (match_id, event_type, target, int(datetime.now().timestamp()))
            )
            conn.commit()

        await interaction.response.send_message(
            f"✅ Recorded {event_type} event for match {match_id}: {target}",
            ephemeral=False
        )

        # Also announce in the log channel
        await bot.get_channel(bot.log_channel_id).send(
            f"📊 **Match Event Recorded**\n"
            f"Match: {match_id}\n"
            f"Event: {event_type}\n"
            f"Target: {target}"
        )

        # Trigger bet resolution if needed
        if event_type == "first_blood":
            from betting.resolver import resolve_first_blood_bets
            await resolve_first_blood_bets(bot, match_id, target)
        elif event_type == "mvp":
            from betting.resolver import resolve_mvp_bets
            await resolve_mvp_bets(bot, match_id, target)
        elif event_type == "winner":
            from betting.resolver import resolve_match_team_win_bets
            await resolve_match_team_win_bets(bot, match_id, target)

    @bot.tree.command(name="resolve_match", description="Admin-only: Manually resolve a match")
    @app_commands.describe(
        match_id="The match ID to resolve",
        winner="The winning team (team1 or team2)"
    )
    async def resolve_match(interaction: discord.Interaction, match_id: str, winner: str):
        """Manually resolve a match and its bets."""
        # Admin-only check
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ This command is for administrators only.", ephemeral=True)
            return

        # Validate winner input
        if winner not in ["team1", "team2"]:
            await interaction.response.send_message("❌ Winner must be either 'team1' or 'team2'.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        # Record the winner event
        with get_db_connection() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO match_events (match_id, event_type, event_target, event_time) VALUES (?, ?, ?, ?)',
                (match_id, "winner", winner, int(datetime.now().timestamp()))
            )
            conn.commit()

        # Resolve the match bets
        from betting.resolver import resolve_match_team_win_bets
        await resolve_match_team_win_bets(bot, match_id, winner)

        # Notify the channel
        await interaction.followup.send(
            f"✅ Match {match_id} has been manually resolved with {winner} as the winner.\n"
            f"All team win bets for this match have been processed."
        )

        # Also add to completed matches set to prevent re-detection
        bot.completed_matches.add(match_id)

    @bot.tree.command(name="check_gsi", description="Check if Game State Integration is working")
    async def check_gsi(interaction: discord.Interaction):
        """Test if GSI is correctly set up for the user."""
        user_id = interaction.user.id

        await interaction.response.defer(ephemeral=True)

        # First check if Steam ID is linked
        if user_id not in bot.steam_ids_cache:
            await interaction.followup.send(
                "❌ You need to link your Steam ID first with `/link_steam <url>`",
            )
            return

        # Check for any GSI data received in the last 30 minutes
        gsi_status = "❌ Not detected"

        # Check if ngrok is working
        ngrok_url = bot.ngrok_url if hasattr(bot, 'ngrok_url') else None
        if ngrok_url:
            ngrok_status = f"✅ Working at {ngrok_url}/gsi/dota2"
        else:
            ngrok_status = "❌ Not running"

        # Check database for recent GSI activity
        with get_db_connection() as conn:
            # Check for GSI connections
            conn_exists = False
            for table in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                if table[0] == 'gsi_connections':
                    conn_exists = True
                    break

            if conn_exists:
                thirty_min_ago = (datetime.now() - timedelta(minutes=30)).isoformat()
                recent_gsi = conn.execute(
                    'SELECT COUNT(*) as count FROM gsi_connections WHERE user_id = ? AND timestamp > ?',
                    (user_id, thirty_min_ago)
                ).fetchone()

                if recent_gsi and recent_gsi['count'] > 0:
                    gsi_status = f"✅ Working (received {recent_gsi['count']} updates in last 30 minutes)"

        # Build response
        response = (
            "# GSI Connection Status\n\n"
            f"**GSI Communication**: {gsi_status}\n"
            f"**Server Status**: {ngrok_status}\n\n"
        )

        # Add troubleshooting steps if not working
        if "❌" in gsi_status:
            response += (
                "## Troubleshooting Steps\n\n"
                "1. **Verify file location**: Double-check the config file is in the correct folder\n"
                "2. **Check file name**: Make sure it's exactly `gamestate_integration_goodgains.cfg`\n"
                "3. **Restart Dota 2**: Changes only take effect after restarting\n"
                "4. **Check connection**: Make sure your computer can reach our server\n"
                "5. **Start a match**: GSI only sends data during actual matches\n\n"

                "Run `/setup_gsi` again to get a fresh config file and detailed setup instructions."
            )

        await interaction.followup.send(response)

    logger.info("Admin commands registered")
    return bot