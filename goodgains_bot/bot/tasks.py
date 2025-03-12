import asyncio
import logging
from datetime import datetime, timedelta
from discord.ext import tasks
from database.connection import get_db_connection
from api.dota import get_match_details
from bot.bot import active_players_lock
from betting.resolver import resolve_match_team_win_bets, check_event_based_bets

logger = logging.getLogger('goodgains_bot')


def start_tasks(bot):
    """Start all background tasks."""
    # Game activity monitoring
    check_game_activity.start(bot)

    # Bet resolution
    resolve_bets.start(bot)

    # Maintenance tasks
    cleanup_stale_matches.start(bot)
    clean_expired_sessions.start(bot)
    maintain_match_caches.start(bot)

    # User engagement
    send_weekly_summaries.start(bot)
    check_inactive_users.start(bot)


@tasks.loop(seconds=15)
async def check_game_activity(bot):
    """Check for active Dota 2 games."""
    await bot.wait_until_ready()

    try:
        with get_db_connection() as conn:
            # Get all registered Steam IDs
            steam_mappings = conn.execute('SELECT user_id, steam_id FROM steam_mappings').fetchall()

        # Process in small batches to avoid overwhelming the API
        batch_size = 5
        for i in range(0, len(steam_mappings), batch_size):
            batch = steam_mappings[i:i + batch_size]
            tasks = []

            for mapping in batch:
                user_id = mapping['user_id']
                steam_id = mapping['steam_id']

                # Add rate limiting check
                if user_id in bot.active_players_cache:
                    last_check = bot.active_players_cache[user_id].get('last_check_time', 0)
                    current_time = int(datetime.now().timestamp())

                    # Only check every 60 seconds unless they're not in a match
                    if current_time - last_check < 60 and 'match_id' in bot.active_players_cache[user_id]:
                        continue

                tasks.append(check_dota2_match(bot, user_id, steam_id))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(1)  # Brief pause between batches

    except Exception as e:
        logger.error(f"Error in check_game_activity task: {e}")


async def check_dota2_match(bot, user_id, steam_id):
    """Check if a user is in a Dota 2 match."""
    from api.dota import get_match_history, get_live_league_games
    from utils.notifications import send_match_notification

    account_id = int(steam_id) - 76561197960265728  # Convert to Dota 2 account ID
    logger.info(f"Checking Dota 2 match status for user {user_id} (account_id: {account_id})")

    current_time = int(datetime.now().timestamp())

    # First check if user is already tracked in a match
    with get_db_connection() as conn:
        current_match = conn.execute(
            'SELECT match_id, match_start_time FROM active_players WHERE user_id = ?',
            (user_id,)
        ).fetchone()

    if current_match:
        # Validate if the tracked match is truly active
        match_id = current_match['match_id']
        match_details = await get_match_details(match_id)

        # If match has ended, clean it up
        if match_details and match_details.get('status') == 'completed':
            logger.info(f"User {user_id} cleanup: match {match_id} is no longer active")

            # Add to completed matches to prevent immediate re-detection
            bot.completed_matches.add(match_id)
            bot.recently_cleaned_matches[match_id] = current_time

            with get_db_connection() as conn:
                conn.execute('DELETE FROM active_players WHERE user_id = ?', (user_id,))
                conn.commit()

            with active_players_lock:
                if user_id in bot.active_players_cache:
                    del bot.active_players_cache[user_id]
        else:
            # Match still appears active, update last check time
            with active_players_lock:
                if user_id in bot.active_players_cache:
                    bot.active_players_cache[user_id]['last_check_time'] = current_time
            return True

    # Check if player is in a league match
    league_games = await get_live_league_games()
    if league_games:
        for game in league_games:
            for player in game.get('players', []):
                if player.get('account_id') == account_id:
                    match_id = str(game['match_id'])
                    team = "team1" if player.get('team', 0) == 0 else "team2"

                    logger.info(f"Found user {user_id} in league match {match_id}")
                    await update_player_match(bot, user_id, "570", match_id, team, "League Match")
                    return True

    # Check recent matches
    recent_matches = await get_match_history(account_id, 3)
    if recent_matches:
        for match in recent_matches:
            match_id = str(match.get('match_id'))
            start_time = match.get('start_time', 0)

            # Only consider recent matches (last 30 minutes)
            if current_time - start_time > 1800:  # 30 minutes
                continue

            # Check if match is still ongoing
            match_details = await get_match_details(match_id)
            if match_details and match_details.get('status') == 'in_progress':
                # Determine player's team
                for player in match.get('players', []):
                    if player.get('account_id') == account_id:
                        team = "team1" if player.get('player_slot', 0) < 128 else "team2"
                        logger.info(f"Found user {user_id} in active match {match_id}")
                        await update_player_match(bot, user_id, "570", match_id, team, "Public Match", start_time)
                        return True

    return False


async def update_player_match(bot, user_id, game_id, match_id, team, match_type, match_start_time=None):
    """Update the database and cache with player match information."""
    # If no start time provided, use current time
    if match_start_time is None:
        match_start_time = int(datetime.now().timestamp())

    try:
        # Check if we're already tracking this match for this user
        with get_db_connection() as conn:
            existing_match = conn.execute(
                'SELECT match_id FROM active_players WHERE user_id = ?',
                (user_id,)
            ).fetchone()

            # If already in this exact match, don't update or notify again
            if existing_match and existing_match['match_id'] == match_id:
                # Just update the last check time in the cache
                with active_players_lock:
                    if user_id in bot.active_players_cache:
                        bot.active_players_cache[user_id]['last_check_time'] = int(datetime.now().timestamp())
                logger.info(f"User {user_id} already being tracked in match {match_id}, skipping update")
                return

        # Update database for new match
        with get_db_connection() as conn:
            # First remove any existing active matches for this user
            conn.execute('DELETE FROM active_players WHERE user_id = ?', (user_id,))

            # Then insert the new match
            conn.execute(
                'INSERT INTO active_players (user_id, game_id, match_id, team, match_start_time) VALUES (?, ?, ?, ?, ?)',
                (user_id, game_id, match_id, team, match_start_time)
            )
            conn.commit()
            logger.info(f"Database updated for user {user_id} in match {match_id}")

        # Update cache
        current_time = int(datetime.now().timestamp())
        with active_players_lock:
            bot.active_players_cache[user_id] = {
                "game_id": game_id,
                "match_id": match_id,
                "team": team,
                "match_start_time": match_start_time,
                "last_check_time": current_time
            }
            logger.info(f"Cache updated for user {user_id} in match {match_id}")

        logger.info(f"User {user_id} is in Dota 2 {match_type} {match_id} on {team}")

        # Send notification
        from utils.notifications import send_match_notification
        await send_match_notification(bot, user_id, match_id, team, match_type)

    except Exception as e:
        logger.error(f"Error in update_player_match: {e}")


@tasks.loop(minutes=5)
async def resolve_bets(bot):
    """Resolve pending bets for matches that have ended."""
    await bot.wait_until_ready()
    logger.info("Resolving pending bets...")

    with get_db_connection() as conn:
        # Get distinct match IDs with unresolved bets
        pending_matches = conn.execute(
            'SELECT DISTINCT match_id FROM bets WHERE resolved = FALSE'
        ).fetchall()

        for match in pending_matches:
            match_id = match['match_id']

            # Skip legacy synthetic matches
            if match_id.startswith("dota_") or match_id.startswith("sim_"):
                logger.warning(f"Found legacy synthetic match ID {match_id} - skipping automatic resolution")
                continue

            # Check if match has concluded
            match_details = await get_match_details(match_id)

            if match_details and match_details.get('status') == 'completed':
                winning_team = match_details.get('winner')

                if winning_team:
                    await resolve_match_team_win_bets(bot, match_id, winning_team)

            # Check for event-based bets (first_blood, mvp, etc.)
            await check_event_based_bets(bot, match_id)


@tasks.loop(minutes=10)
async def cleanup_stale_matches(bot):
    """Check and clean up stale match entries."""
    await bot.wait_until_ready()
    logger.info("Cleaning up stale matches...")

    current_time = int(datetime.now().timestamp())
    MAX_MATCH_DURATION = 7200  # 2 hours in seconds

    with get_db_connection() as conn:
        active_players = conn.execute(
            'SELECT user_id, match_id, match_start_time FROM active_players'
        ).fetchall()

    for player in active_players:
        user_id = player['user_id']
        match_id = player['match_id']
        match_start_time = player['match_start_time']

        # First check absolute match duration - force cleanup if too old
        match_duration = current_time - match_start_time
        if match_duration > MAX_MATCH_DURATION:
            logger.info(f"Cleanup: Match {match_id} for user {user_id} exceeded maximum duration")

            # Remove from database
            with get_db_connection() as conn:
                conn.execute('DELETE FROM active_players WHERE user_id = ?', (user_id,))
                conn.commit()

            # Remove from cache
            with active_players_lock:
                if user_id in bot.active_players_cache:
                    del bot.active_players_cache[user_id]

            # Notify log channel
            try:
                await bot.get_channel(bot.log_channel_id).send(
                    f"⏱️ <@{user_id}>'s match {match_id} has been automatically closed after exceeding maximum duration."
                )
            except Exception as e:
                logger.error(f"Failed to send cleanup notification: {e}")

            continue  # Skip further validation

        # For matches within reasonable duration, check if they're actually active
        match_details = await get_match_details(match_id)

        if match_details and match_details.get('status') == 'completed':
            logger.info(f"Cleanup: Match {match_id} for user {user_id} is no longer active")

            # Add to completed matches set
            bot.completed_matches.add(match_id)

            # Remove from database
            with get_db_connection() as conn:
                conn.execute('DELETE FROM active_players WHERE user_id = ?', (user_id,))
                conn.commit()

            # Remove from cache
            with active_players_lock:
                if user_id in bot.active_players_cache:
                    del bot.active_players_cache[user_id]

            # Notify log channel
            try:
                await bot.get_channel(bot.log_channel_id).send(
                    f"🏁 <@{user_id}> is no longer in match {match_id} (detected during cleanup)."
                )
            except Exception as e:
                logger.error(f"Failed to send cleanup notification: {e}")


@tasks.loop(minutes=15)
async def clean_expired_sessions(bot):
    """Clean up expired wallet sessions."""
    await bot.wait_until_ready()
    logger.info("Cleaning expired wallet sessions...")

    with get_db_connection() as conn:
        # Find sessions older than 24 hours
        cutoff = datetime.now() - timedelta(hours=24)
        conn.execute(
            'DELETE FROM wallet_sessions WHERE last_active < ? AND connected = FALSE',
            (cutoff.isoformat(),)
        )
        conn.commit()

    # Reload caches
    bot.reload_caches()


@tasks.loop(hours=24 * 7)  # Run once a week
async def send_weekly_summaries(bot):
    """Send weekly betting summaries to active users."""
    await bot.wait_until_ready()
    logger.info("Sending weekly summaries...")

    # Get date range for past week
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    with get_db_connection() as conn:
        # Find users who placed bets in the last month (to avoid messaging inactive users)
        active_users = conn.execute(
            '''SELECT DISTINCT user_id FROM bets 
            WHERE placed_at > ?''',
            ((end_date - timedelta(days=30)).isoformat(),)
        ).fetchall()

        for user in active_users:
            user_id = user['user_id']

            # Get weekly stats
            weekly_stats = conn.execute(
                '''SELECT 
                    COUNT(*) AS total_bets,
                    SUM(amount) AS total_wagered,
                    SUM(CASE WHEN won = TRUE THEN 1 ELSE 0 END) AS wins,
                    SUM(payout) AS total_winnings
                FROM bets 
                WHERE user_id = ? AND placed_at BETWEEN ? AND ?''',
                (user_id, start_date.isoformat(), end_date.isoformat())
            ).fetchone()

            # Skip users with no activity this week
            if weekly_stats['total_bets'] == 0:
                continue

            # Calculate profit/loss
            profit = (weekly_stats['total_winnings'] or 0) - (weekly_stats['total_wagered'] or 0)
            win_rate = (weekly_stats['wins'] / weekly_stats['total_bets'] * 100) if weekly_stats[
                                                                                        'total_bets'] > 0 else 0

            # Format and send the message
            message = (
                f"📊 **Your Weekly Betting Summary**\n\n"
                f"**Period:** {start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}\n\n"
                f"**Activity:**\n"
                f"• Total Bets: {weekly_stats['total_bets']}\n"
                f"• Win Rate: {win_rate:.1f}%\n"
                f"• Amount Wagered: {weekly_stats['total_wagered']:.4f} ETH\n"
                f"• Profit/Loss: {profit:+.4f} ETH\n\n"
                f"Keep up the good work! Remember to check `/profile` for your all-time stats."
            )

            await bot.send_direct_message(user_id, message)
            logger.info(f"Sent weekly summary to user {user_id}")


@tasks.loop(hours=24)
async def check_inactive_users(bot):
    """Send reminders to users who haven't placed bets recently."""
    await bot.wait_until_ready()
    logger.info("Checking for inactive users...")

    # Define inactivity threshold (14 days)
    threshold = (datetime.now() - timedelta(days=14)).isoformat()

    with get_db_connection() as conn:
        # Find previously active users who haven't bet recently
        inactive_users = conn.execute(
            '''SELECT user_id, MAX(placed_at) as last_bet,
                (SELECT COUNT(*) FROM bets WHERE user_id = b.user_id) as total_bets
            FROM bets b
            GROUP BY user_id
            HAVING MAX(placed_at) < ? AND total_bets > 3''',
            (threshold,)
        ).fetchall()

        for user in inactive_users:
            # Check if they're a regular user worth reminding (placed several bets)
            if user['total_bets'] < 3:
                continue

            # Calculate days since last activity
            last_bet_date = datetime.fromisoformat(user['last_bet'])
            days_inactive = (datetime.now() - last_bet_date).days

            # Send personalized reminder
            message = (
                f"👋 **We Miss You!**\n\n"
                f"It's been **{days_inactive} days** since your last bet. We hope you'll join us again soon!\n\n"
                f"**What's new:**\n"
                f"• Several users won big recently\n"
                f"• Betting mechanisms have been optimized\n"
                f"• New types of bets coming soon\n\n"
                f"Ready to jump back in? Use `/check_match` next time you're playing Dota 2!"
            )

            await bot.send_direct_message(user['user_id'], message)
            logger.info(f"Sent inactivity reminder to user {user['user_id']} ({days_inactive} days inactive)")


@tasks.loop(minutes=30)
async def maintain_match_caches(bot):
    """Clean up cached match tracking data periodically."""
    await bot.wait_until_ready()
    logger.info("Maintaining match caches...")

    current_time = int(datetime.now().timestamp())

    # Clean up recently_cleaned_matches (keep items from last 20 minutes)
    cleanup_threshold = current_time - 1200  # 20 minutes
    removed = 0
    for match_id in list(bot.recently_cleaned_matches.keys()):
        if bot.recently_cleaned_matches[match_id] < cleanup_threshold:
            del bot.recently_cleaned_matches[match_id]
            removed += 1

    # Keep completed_matches from growing too large (limit to 2000 most recent matches)
    if len(bot.completed_matches) > 2000:
        logger.info(f"Pruning completed_matches cache from {len(bot.completed_matches)} to 2000 entries")
        # Convert to list, sort by time added (if available), and keep most recent
        bot.completed_matches = set(list(bot.completed_matches)[-2000:])

    logger.info(f"Maintenance: Removed {removed} old entries from recently_cleaned_matches")