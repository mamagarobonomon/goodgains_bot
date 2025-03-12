import logging
import asyncio
from datetime import datetime
from database.connection import get_db_connection

logger = logging.getLogger('goodgains_bot')


async def process_dota2_gsi_data(data, user_id=None, bot=None):
    """Process Dota 2 GSI data with better event handling and match tracking."""
    try:
        # Extract match ID from data
        match_id = data.get('map', {}).get('matchid')
        if not match_id:
            logger.warning("Received GSI data without match ID")
            return

        # Extract game state
        game_state = data.get('map', {}).get('game_state')

        # Log basic match info
        logger.info(f"Processing GSI data for match {match_id}, state: {game_state}")

        # Check for player information
        player_team = None
        player_name = None
        if 'player' in data:
            player_data = data['player']
            player_team = 'team1' if player_data.get('team_name', '').lower() == 'radiant' else 'team2'
            player_name = player_data.get('name', 'Unknown')

            # If we have a user_id and we know the player is in a match, update their status
            if user_id and game_state and game_state not in ['undefined', 'postgame']:
                match_start_time = int(datetime.now().timestamp())
                if 'map' in data and 'clock_time' in data['map']:
                    # Adjust start time based on game clock
                    clock_seconds = int(data['map']['clock_time'])
                    match_start_time = match_start_time - clock_seconds

                with get_db_connection() as conn:
                    # Check if already tracking this match
                    existing = conn.execute(
                        'SELECT 1 FROM active_players WHERE user_id = ? AND match_id = ?',
                        (user_id, match_id)
                    ).fetchone()

                    if not existing:
                        conn.execute(
                            'INSERT OR REPLACE INTO active_players (user_id, game_id, match_id, team, match_start_time) VALUES (?, ?, ?, ?, ?)',
                            (user_id, '570', match_id, player_team, match_start_time)
                        )
                        conn.commit()

                        # Also update the cache if bot is available
                        if bot:
                            from bot.bot import active_players_lock
                            with active_players_lock:
                                bot.active_players_cache[user_id] = {
                                    'game_id': '570',
                                    'match_id': match_id,
                                    'team': player_team,
                                    'match_start_time': match_start_time,
                                    'last_check_time': int(datetime.now().timestamp())
                                }

                            # Send notification about the new match
                            from utils.notifications import send_match_notification
                            await send_match_notification(
                                bot,
                                user_id,
                                match_id,
                                player_team,
                                "Public Match"
                            )
                        logger.info(f"GSI: Detected user {user_id} in Dota 2 match {match_id} on {player_team}")

        # Process game events
        if 'events' in data:
            events = data['events']

            # First blood event
            if events.get('first_blood') and not events.get('first_blood_claimed', False):
                # Use player name from event if available
                first_blood_player = events.get('first_blood_player', 'Unknown')

                # If not available, try to derive from other data
                if first_blood_player == 'Unknown' and 'player' in data:
                    if data['player'].get('kills', 0) > 0:
                        first_blood_player = data['player'].get('name', 'Unknown')

                # Record the event
                with get_db_connection() as conn:
                    # Check if this event already recorded
                    existing = conn.execute(
                        'SELECT 1 FROM match_events WHERE match_id = ? AND event_type = "first_blood"',
                        (match_id,)
                    ).fetchone()

                    if not existing:
                        conn.execute(
                            'INSERT INTO match_events (match_id, event_type, event_target, event_time) VALUES (?, ?, ?, ?)',
                            (match_id, "first_blood", first_blood_player, int(datetime.now().timestamp()))
                        )
                        conn.commit()

                        logger.info(f"GSI: Recorded first blood by {first_blood_player} in match {match_id}")

                        # Mark as claimed so we don't process again
                        events['first_blood_claimed'] = True

                        # Trigger bet resolution for first blood bets if bot is available
                        if bot:
                            from betting.resolver import resolve_first_blood_bets
                            asyncio.create_task(resolve_first_blood_bets(bot, match_id, first_blood_player))

            # Game end and winner determination
            if game_state == 'postgame':
                logger.info(f"GSI: Match {match_id} ended")

                # Record match end
                with get_db_connection() as conn:
                    # Check if end already recorded
                    existing = conn.execute(
                        'SELECT 1 FROM match_events WHERE match_id = ? AND event_type = "match_end"',
                        (match_id,)
                    ).fetchone()

                    if not existing:
                        conn.execute(
                            'INSERT INTO match_events (match_id, event_type, event_target, event_time) VALUES (?, ?, ?, ?)',
                            (match_id, "match_end", "", int(datetime.now().timestamp()))
                        )
                        conn.commit()

                # Determine winner if available
                if 'map' in data and 'win_team' in data['map']:
                    win_team = data['map']['win_team']
                    winning_team = "team1" if win_team.lower() == 'radiant' else "team2"

                    with get_db_connection() as conn:
                        # Check if winner already recorded
                        existing = conn.execute(
                            'SELECT 1 FROM match_events WHERE match_id = ? AND event_type = "winner"',
                            (match_id,)
                        ).fetchone()

                        if not existing:
                            conn.execute(
                                'INSERT INTO match_events (match_id, event_type, event_target, event_time) VALUES (?, ?, ?, ?)',
                                (match_id, "winner", winning_team, int(datetime.now().timestamp()))
                            )
                            conn.commit()

                    logger.info(f"GSI: Recorded match {match_id} winner: {winning_team}")

                    # Trigger bet resolution for team win bets if bot is available
                    if bot:
                        from betting.resolver import resolve_match_team_win_bets
                        asyncio.create_task(resolve_match_team_win_bets(bot, match_id, winning_team))

                # Try to determine MVP based on available stats
                if 'players' in data:
                    try:
                        determine_mvp(data, match_id)
                    except Exception as e:
                        logger.error(f"Error determining MVP: {e}")

                # If user_id provided, remove from active players
                if user_id:
                    with get_db_connection() as conn:
                        conn.execute('DELETE FROM active_players WHERE user_id = ? AND match_id = ?',
                                     (user_id, match_id))
                        conn.commit()

                    # Also update cache if bot is available
                    if bot:
                        from bot.bot import active_players_lock
                        with active_players_lock:
                            if user_id in bot.active_players_cache:
                                del bot.active_players_cache[user_id]

                    logger.info(f"GSI: Removed user {user_id} from active players as match {match_id} ended")

        return True

    except Exception as e:
        logger.error(f"Error processing GSI data: {e}")
        # Log full traceback for debugging
        import traceback
        logger.error(traceback.format_exc())
        return False


def determine_mvp(data, match_id):
    """Determine MVP based on game statistics."""
    players_dict = data.get('players', {})
    win_team = data.get('map', {}).get('win_team', '').lower()

    # Create scoring system to determine MVP
    player_scores = {}

    for player_id, player_data in players_dict.items():
        if not isinstance(player_data, dict):
            continue

        # Create a score based on key performance indicators
        score = 0
        score += player_data.get('kills', 0) * 4
        score += player_data.get('assists', 0) * 2
        score -= player_data.get('deaths', 0) * 3
        score += player_data.get('net_worth', 0) / 200
        score += player_data.get('gpm', 0) / 10
        score += player_data.get('xpm', 0) / 10

        # Add additional weight for the winning team
        if 'team_name' in player_data:
            if (player_data['team_name'].lower() == 'radiant' and win_team == 'radiant') or \
                    (player_data['team_name'].lower() == 'dire' and win_team == 'dire'):
                score *= 1.5

        # Get player name
        player_name = player_data.get('name', f"Player_{player_id}")
        player_scores[player_name] = score

    # Find player with highest score
    if player_scores:
        mvp_name = max(player_scores.items(), key=lambda x: x[1])[0]

        with get_db_connection() as conn:
            # Check if MVP already recorded
            existing = conn.execute(
                'SELECT 1 FROM match_events WHERE match_id = ? AND event_type = "mvp"',
                (match_id,)
            ).fetchone()

            if not existing:
                conn.execute(
                    'INSERT INTO match_events (match_id, event_type, event_target, event_time) VALUES (?, ?, ?, ?)',
                    (match_id, "mvp", mvp_name, int(datetime.now().timestamp()))
                )
                conn.commit()

        logger.info(f"GSI: Determined MVP {mvp_name} in match {match_id}")
        return mvp_name

    return None