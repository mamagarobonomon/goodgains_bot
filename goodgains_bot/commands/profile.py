import discord
from discord import app_commands
import logging
from datetime import datetime
from database.connection import get_db_connection

logger = logging.getLogger('goodgains_bot')


def register_commands(bot):
    """Register profile-related commands."""

    @bot.tree.command(name="profile", description="View your betting profile and history")
    @app_commands.describe(
        user="Optional: View another user's profile (admin only)",
        private="Set to True to show your profile only to yourself"
    )
    async def profile(interaction: discord.Interaction, user: discord.User = None, private: bool = False):
        """View betting profile and history for yourself or another user (admins only)."""

        # Handle permissions for viewing other users' profiles
        target_user = user if user else interaction.user
        if user and user != interaction.user and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can view other users' profiles.",
                                                    ephemeral=True)
            return

        # Use ephemeral response if private or viewing someone else's profile as admin
        is_ephemeral = private or (user and user != interaction.user)
        await interaction.response.defer(ephemeral=is_ephemeral)

        # Gather all profile data
        user_id = target_user.id

        with get_db_connection() as conn:
            # Get wallet information
            wallet = conn.execute(
                'SELECT wallet_address FROM wallet_sessions WHERE user_id = ? AND connected = TRUE',
                (user_id,)
            ).fetchone()

            # Get Steam info
            steam = conn.execute(
                'SELECT steam_id, created_at FROM steam_mappings WHERE user_id = ?',
                (user_id,)
            ).fetchone()

            # Get betting statistics
            stats = conn.execute(
                '''SELECT 
                    COUNT(*) AS total_bets,
                    SUM(amount) AS total_wagered,
                    SUM(CASE WHEN won = TRUE THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN won = FALSE AND resolved = TRUE THEN 1 ELSE 0 END) AS losses,
                    SUM(CASE WHEN resolved = FALSE THEN 1 ELSE 0 END) AS pending,
                    SUM(payout) AS total_winnings
                FROM bets 
                WHERE user_id = ?''',
                (user_id,)
            ).fetchone()

            # Get bet type distribution
            bet_types = conn.execute(
                '''SELECT 
                    bet_type, 
                    COUNT(*) as count,
                    SUM(CASE WHEN won = TRUE THEN 1 ELSE 0 END) AS wins
                FROM bets 
                WHERE user_id = ? 
                GROUP BY bet_type''',
                (user_id,)
            ).fetchall()

            # Get recent betting history (10 most recent bets)
            recent_bets = conn.execute(
                '''SELECT 
                    match_id, 
                    bet_type, 
                    amount, 
                    team,
                    target,
                    placed_at, 
                    resolved, 
                    won, 
                    payout 
                FROM bets 
                WHERE user_id = ? 
                ORDER BY placed_at DESC 
                LIMIT 10''',
                (user_id,)
            ).fetchall()

        # Calculate win rate and profit
        wins = stats['wins'] or 0
        total_resolved = (stats['wins'] or 0) + (stats['losses'] or 0)
        win_rate = (wins / total_resolved * 100) if total_resolved > 0 else 0
        profit = (stats['total_winnings'] or 0) - (stats['total_wagered'] or 0)
        profit_percentage = (profit / stats['total_wagered'] * 100) if stats['total_wagered'] and stats[
            'total_wagered'] > 0 else 0

        # Create a formatted embed
        embed = discord.Embed(
            title=f"Betting Profile: {target_user.display_name}",
            description=f"Member since {target_user.created_at.strftime('%b %d, %Y')}",
            color=0x3498db  # Blue color
        )

        # Add user's avatar
        embed.set_thumbnail(url=target_user.display_avatar.url)

        # Account Section
        account_info = []
        if wallet and wallet['wallet_address']:
            wallet_short = f"{wallet['wallet_address'][:6]}...{wallet['wallet_address'][-4:]}"
            account_info.append(f"**Wallet**: `{wallet_short}`")
        else:
            account_info.append("**Wallet**: Not connected")

        if steam and steam['steam_id']:
            steam_profile = f"https://steamcommunity.com/profiles/{steam['steam_id']}"
            account_info.append(f"**Steam**: [Profile]({steam_profile})")
        else:
            account_info.append("**Steam**: Not linked")

        embed.add_field(name="Account", value="\n".join(account_info), inline=False)

        # Stats Section
        stats_info = [
            f"**Total Bets**: {stats['total_bets'] or 0}",
            f"**Total Wagered**: {stats['total_wagered'] or 0:.4f} ETH",
            f"**Win Rate**: {win_rate:.1f}% ({wins}/{total_resolved})",
            f"**Profit/Loss**: {profit:.4f} ETH ({profit_percentage:+.1f}%)",
            f"**Pending Bets**: {stats['pending'] or 0}"
        ]
        embed.add_field(name="Statistics", value="\n".join(stats_info), inline=False)

        # Bet Type Distribution
        if bet_types:
            bet_type_names = {
                "team_win": "Team Wins",
                "first_blood": "First Blood",
                "mvp": "MVP"
            }

            type_info = []
            for bet_type in bet_types:
                type_name = bet_type_names.get(bet_type['bet_type'], bet_type['bet_type'])
                win_rate = (bet_type['wins'] / bet_type['count'] * 100) if bet_type['count'] > 0 else 0
                type_info.append(f"**{type_name}**: {bet_type['count']} bets ({win_rate:.1f}% win rate)")

            embed.add_field(name="Bet Types", value="\n".join(type_info), inline=False)

        # Recent Bets
        if recent_bets:
            bet_history = []
            for bet in recent_bets:
                # Format the bet information based on type
                if bet['bet_type'] == 'team_win':
                    bet_desc = f"**{bet['team']}** to win"
                elif bet['bet_type'] == 'first_blood':
                    bet_desc = f"**{bet['target']}** for First Blood"
                elif bet['bet_type'] == 'mvp':
                    bet_desc = f"**{bet['target']}** for MVP"
                else:
                    bet_desc = f"{bet['bet_type']}"

                # Format status and result
                if not bet['resolved']:
                    status = "⏳ Pending"
                elif bet['won']:
                    status = f"✅ Won {bet['payout']:.4f} ETH"
                else:
                    status = "❌ Lost"

                # Format date
                date = datetime.fromisoformat(bet['placed_at']).strftime("%m/%d/%y")

                bet_history.append(f"**{date}**: {bet['amount']:.4f} ETH on {bet_desc} - {status}")

            embed.add_field(name="Recent Bets", value="\n".join(bet_history[:5]), inline=False)

            # Add a second field if there are more bets to show
            if len(bet_history) > 5:
                embed.add_field(name="More Recent Bets", value="\n".join(bet_history[5:]), inline=False)
        else:
            embed.add_field(name="Recent Bets", value="No bets placed yet.", inline=False)

        # Footer with timestamp
        embed.set_footer(text=f"Profile updated • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Send the embed
        await interaction.followup.send(embed=embed)
        logger.info(f"Profile viewed for user {user_id} by {interaction.user.id}")

    logger.info("Profile commands registered")
    return bot