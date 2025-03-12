import logging
from datetime import datetime, timedelta
from database.connection import get_db_connection
from config import MIN_BET_AMOUNT, MAX_BET_AMOUNT, MAX_BETS_PER_HOUR

logger = logging.getLogger('goodgains_bot')


async def place_team_win_bet(user_id, match_id, team, amount):
    """Place a bet on team winning a match."""
    # Validate bet amount
    if amount < MIN_BET_AMOUNT:
        return {"success": False, "message": f"Minimum bet is {MIN_BET_AMOUNT} ETH."}

    if amount > MAX_BET_AMOUNT:
        return {"success": False, "message": f"Maximum bet is {MAX_BET_AMOUNT} ETH."}

    # Check rate limiting
    if not await check_bet_rate_limit(user_id):
        return {"success": False, "message": f"You've reached the maximum of {MAX_BETS_PER_HOUR} bets per hour."}

    # Place bet in database
    try:
        with get_db_connection() as conn:
            conn.execute(
                'INSERT INTO bets (user_id, match_id, bet_type, team, amount) VALUES (?, ?, ?, ?, ?)',
                (user_id, match_id, "team_win", team, amount)
            )
            conn.commit()

        logger.info(f"User {user_id} placed {amount} ETH bet on {team} in match {match_id}")
        return {"success": True, "message": f"You bet {amount} ETH on {team} in match {match_id}!"}

    except Exception as e:
        logger.error(f"Error placing team win bet: {e}")
        return {"success": False, "message": "An error occurred while placing your bet."}


async def place_first_blood_bet(user_id, match_id, player, amount):
    """Place a bet on a player getting first blood."""
    # Validate bet amount
    if amount < MIN_BET_AMOUNT:
        return {"success": False, "message": f"Minimum bet is {MIN_BET_AMOUNT} ETH."}

    if amount > MAX_BET_AMOUNT:
        return {"success": False, "message": f"Maximum bet is {MAX_BET_AMOUNT} ETH."}

    # Check rate limiting
    if not await check_bet_rate_limit(user_id):
        return {"success": False, "message": f"You've reached the maximum of {MAX_BETS_PER_HOUR} bets per hour."}

    # Place bet in database
    try:
        with get_db_connection() as conn:
            conn.execute(
                'INSERT INTO bets (user_id, match_id, bet_type, target, amount) VALUES (?, ?, ?, ?, ?)',
                (user_id, match_id, "first_blood", player, amount)
            )
            conn.commit()

        logger.info(f"User {user_id} placed {amount} ETH bet on {player} getting First Blood in match {match_id}")
        return {"success": True,
                "message": f"You bet {amount} ETH that {player} will get First Blood in match {match_id}!"}

    except Exception as e:
        logger.error(f"Error placing first blood bet: {e}")
        return {"success": False, "message": "An error occurred while placing your bet."}


async def place_mvp_bet(user_id, match_id, player, amount):
    """Place a bet on a player being MVP."""
    # Validate bet amount
    if amount < MIN_BET_AMOUNT:
        return {"success": False, "message": f"Minimum bet is {MIN_BET_AMOUNT} ETH."}

    if amount > MAX_BET_AMOUNT:
        return {"success": False, "message": f"Maximum bet is {MAX_BET_AMOUNT} ETH."}

    # Check rate limiting
    if not await check_bet_rate_limit(user_id):
        return {"success": False, "message": f"You've reached the maximum of {MAX_BETS_PER_HOUR} bets per hour."}

    # Place bet in database
    try:
        with get_db_connection() as conn:
            conn.execute(
                'INSERT INTO bets (user_id, match_id, bet_type, target, amount) VALUES (?, ?, ?, ?, ?)',
                (user_id, match_id, "mvp", player, amount)
            )
            conn.commit()

        logger.info(f"User {user_id} placed {amount} ETH bet on {player} being MVP in match {match_id}")
        return {"success": True, "message": f"You bet {amount} ETH that {player} will be MVP in match {match_id}!"}

    except Exception as e:
        logger.error(f"Error placing MVP bet: {e}")
        return {"success": False, "message": "An error occurred while placing your bet."}


async def check_bet_rate_limit(user_id):
    """Check if user has exceeded the betting rate limit."""
    try:
        with get_db_connection() as conn:
            # Count bets in the last hour
            one_hour_ago = datetime.now() - timedelta(hours=1)
            recent_bets = conn.execute(
                'SELECT COUNT(*) as count FROM bets WHERE user_id = ? AND placed_at > ?',
                (user_id, one_hour_ago.isoformat())
            ).fetchone()

            if recent_bets and recent_bets['count'] >= MAX_BETS_PER_HOUR:
                return False

            # Update rate limit tracking
            conn.execute(
                'INSERT OR REPLACE INTO rate_limits (user_id, action, timestamp) VALUES (?, ?, ?)',
                (user_id, "place_bet", datetime.now().isoformat())
            )
            conn.commit()

            return True

    except Exception as e:
        logger.error(f"Error checking bet rate limit: {e}")
        return False  # Default to preventing bet on error


async def check_active_bets(user_id, match_id):
    """Check if user has already placed bets on this match."""
    try:
        with get_db_connection() as conn:
            existing_bets = conn.execute(
                'SELECT bet_type FROM bets WHERE user_id = ? AND match_id = ?',
                (user_id, match_id)
            ).fetchall()

            return [bet['bet_type'] for bet in existing_bets]

    except Exception as e:
        logger.error(f"Error checking active bets: {e}")
        return []


async def check_betting_window(match_start_time):
    """Check if the betting window is still open (5 minutes from match start)."""
    current_time = int(datetime.now().timestamp())
    time_elapsed = current_time - match_start_time

    # Betting window is 5 minutes (300 seconds)
    if time_elapsed > 300:
        minutes_elapsed = time_elapsed // 60
        return False, f"Betting is only available in the first 5 minutes of the game. This game has been running for approximately {minutes_elapsed} minutes."

    return True, None