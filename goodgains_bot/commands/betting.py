import discord
from discord import app_commands
import logging
from datetime import datetime
from database.connection import get_db_connection
from betting.bets import place_team_win_bet, place_first_blood_bet, place_mvp_bet, check_betting_window
from utils.notifications import send_bet_confirmation

logger = logging.getLogger('goodgains_bot')


def register_commands(bot):
    """Register betting-related commands."""

    @bot.tree.command(name="bet", description="Bet on your team in the current game (available first 5 minutes)")
    @app_commands.describe(amount="Amount to bet in ETH (between 0.01 and 1.0)")
    async def bet(interaction: discord.Interaction, amount: float):
        """Bet on your own team in the current game."""
        user_id = interaction.user.id

        # First, acknowledge the interaction
        await interaction.response.defer(ephemeral=True)

        # Check if user is in a game
        with get_db_connection() as conn:
            active_player = conn.execute(
                'SELECT game_id, match_id, team, match_start_time FROM active_players WHERE user_id = ?',
                (user_id,)
            ).fetchone()

        if not active_player:
            await interaction.followup.send("❌ You must be actively playing a game to place a bet.")
            return

        # Check if betting window is still open
        window_open, message = await check_betting_window(active_player['match_start_time'])
        if not window_open:
            await interaction.followup.send(f"❌ {message}")
            return

        # Check if user has linked Steam
        if user_id not in bot.steam_ids_cache:
            await interaction.followup.send("❌ Register your Steam ID with `/link_steam <url>` first.")
            return

        # Check if user has connected wallet
        with get_db_connection() as conn:
            wallet_session = conn.execute(
                'SELECT wallet_address FROM wallet_sessions WHERE user_id = ? AND connected = TRUE',
                (user_id,)
            ).fetchone()

        if not wallet_session:
            await interaction.followup.send("❌ Connect your wallet with `/connect_wallet` first.")
            return

        # Place the bet
        match_id = active_player['match_id']
        team = active_player['team']

        result = await place_team_win_bet(user_id, match_id, team, amount)

        if result["success"]:
            await interaction.followup.send(f"✅ {result['message']}")

            # Send detailed confirmation
            await send_bet_confirmation(
                bot,
                user_id,
                "team_win",
                amount,
                match_id,
                team=team
            )

            # Notify other bettors
            with get_db_connection() as conn:
                other_bettors = conn.execute(
                    'SELECT DISTINCT user_id FROM bets WHERE match_id = ? AND user_id != ?',
                    (match_id, user_id)
                ).fetchall()

            if other_bettors:
                # Get the username of the new bettor
                user = await bot.fetch_user(user_id)
                username = user.name if user else f"User {user_id}"

                # Format notification for other bettors
                notification = (
                    f"📢 **New Bet Alert**\n\n"
                    f"**{username}** just placed a bet of **{amount} ETH** on **{team}** in match **{match_id}**.\n"
                    f"The pot is growing! Results will be shared after the match ends."
                )

                # Send notification to each previous bettor
                for bettor in other_bettors:
                    await bot.send_direct_message(bettor['user_id'], notification)
        else:
            await interaction.followup.send(f"❌ {result['message']}")

    @bot.tree.command(name="bet_first_blood", description="Bet on who will get First Blood in your Dota 2 match")
    @app_commands.describe(
        player="Name or hero of the player you predict will get First Blood",
        amount="Amount to bet in ETH (between 0.01 and 1.0)"
    )
    async def bet_first_blood(interaction: discord.Interaction, player: str, amount: float):
        """Bet on who will get First Blood in your current Dota 2 match."""
        user_id = interaction.user.id

        # First, acknowledge the interaction
        await interaction.response.defer(ephemeral=True)

        # Check if user is in a Dota 2 game specifically
        with get_db_connection() as conn:
            active_player = conn.execute(
                'SELECT game_id, match_id, team, match_start_time FROM active_players WHERE user_id = ? AND game_id = "570"',
                (user_id,)
            ).fetchone()

        if not active_player:
            await interaction.followup.send("❌ You must be actively playing Dota 2 to place this bet.")
            return

        # Check betting window
        window_open, message = await check_betting_window(active_player['match_start_time'])
        if not window_open:
            await interaction.followup.send(f"❌ {message}")
            return

        # Check if user has connected wallet
        with get_db_connection() as conn:
            wallet_session = conn.execute(
                'SELECT wallet_address FROM wallet_sessions WHERE user_id = ? AND connected = TRUE',
                (user_id,)
            ).fetchone()

        if not wallet_session:
            await interaction.followup.send("❌ Connect your wallet with `/connect_wallet` first.")
            return

        # Place the bet
        match_id = active_player['match_id']

        result = await place_first_blood_bet(user_id, match_id, player, amount)

        if result["success"]:
            await interaction.followup.send(f"✅ {result['message']}")

            # Send detailed confirmation
            await send_bet_confirmation(
                bot,
                user_id,
                "first_blood",
                amount,
                match_id,
                target=player
            )
        else:
            await interaction.followup.send(f"❌ {result['message']}")

    @bot.tree.command(name="bet_mvp", description="Bet on who will be MVP in your Dota 2 match")
    @app_commands.describe(
        player="Name or hero of the player you predict will be MVP",
        amount="Amount to bet in ETH (between 0.01 and 1.0)"
    )
    async def bet_mvp(interaction: discord.Interaction, player: str, amount: float):
        """Bet on who will be MVP in your current Dota 2 match."""
        user_id = interaction.user.id

        # First, acknowledge the interaction
        await interaction.response.defer(ephemeral=True)

        # Check if user is in a Dota 2 game specifically
        with get_db_connection() as conn:
            active_player = conn.execute(
                'SELECT game_id, match_id, team, match_start_time FROM active_players WHERE user_id = ? AND game_id = "570"',
                (user_id,)
            ).fetchone()

        if not active_player:
            await interaction.followup.send("❌ You must be actively playing Dota 2 to place this bet.")
            return

        # Check betting window
        window_open, message = await check_betting_window(active_player['match_start_time'])
        if not window_open:
            await interaction.followup.send(f"❌ {message}")
            return

        # Check if user has connected wallet
        with get_db_connection() as conn:
            wallet_session = conn.execute(
                'SELECT wallet_address FROM wallet_sessions WHERE user_id = ? AND connected = TRUE',
                (user_id,)
            ).fetchone()

        if not wallet_session:
            await interaction.followup.send("❌ Connect your wallet with `/connect_wallet` first.")
            return

        # Place the bet
        match_id = active_player['match_id']

        result = await place_mvp_bet(user_id, match_id, player, amount)

        if result["success"]:
            await interaction.followup.send(f"✅ {result['message']}")

            # Send detailed confirmation
            await send_bet_confirmation(
                bot,
                user_id,
                "mvp",
                amount,
                match_id,
                target=player
            )
        else:
            await interaction.followup.send(f"❌ {result['message']}")

    logger.info("Betting commands registered")
    return bot