import logging
import asyncio
from datetime import datetime
from database.connection import get_db_connection

logger = logging.getLogger('goodgains_bot')


async def process_dota2_gsi_data(data, user_id=None, bot=None):
    """Process Dota 2 GSI data with enhanced match start detection."""
    try:
        # Extract match information
        match_id = data.get('map', {}).get('matchid')
        if not match_id:
            logger.warning("Received GSI data without match ID")
            return False

        # Extract game state
        game_state = data.get('map', {}).get('game_state')

        # Log basic match info
        logger.info(f"Processing GSI data for match {match_id}, state: {game_state}")

        if not user_id or not bot:
            return False

        # Track game state transitions
        transition = detect_game_phases(data, user_id, bot)

        # Handle draft phase detection
        if 'draft' in data and data['draft'].get('activeteam') is not None:
            logger.info(f"Draft phase detected for user {user_id} in match {match_id}")
            with get_db_connection() as conn:
                # Check if already tracking this match
                existing = conn.execute(
                    'SELECT 1 FROM active_players WHERE user_id = ? AND match_id = ?',
                    (user_id, match_id)
                ).fetchone()

                if existing:
                    conn.execute(
                        'UPDATE active_players SET draft_detected_at = ? WHERE user_id = ? AND match_id = ?',
                        (int(datetime.now().timestamp()), user_id, match_id)
                    )
                else:
                    # Get player team information if available
                    player_team = None
                    if 'player' in data:
                        player_data = data['player']
                        player_team = 'team1' if player_data.get('team_name', '').lower() == 'radiant' else 'team2'

                    if player_team:
                        # Create initial match entry with draft phase
                        current_time = int(datetime.now().timestamp())
                        conn.execute(
                            'INSERT INTO active_players (user_id, game_id, match_id, team, match_start_time, draft_detected_at, detection_source) VALUES (?, ?, ?, ?, ?, ?, ?)',
                            (user_id, '570', match_id, player_team, current_time, current_time, 'gsi_draft')
                        )
                conn.commit()

            # Cross-validate with draft detection
            await cross_validate_match_detection(bot, user_id, match_id, 'draft')

            # Send draft notification if not already sent
            if user_id not in bot.game_state_cache or bot.game_state_cache[user_id].get('draft_notified') != match_id:
                await bot.send_direct_message(
                    user_id,
                    f"🎮 **Dota 2 Draft Phase Detected**\n\n"
                    f"You're in the draft phase for match **{match_id}**.\n"
                    f"Get ready to place bets once the game starts!"
                )

                # Mark as notified
                if user_id not in bot.game_state_cache:
                    bot.game_state_cache[user_id] = {}
                bot.game_state_cache[user_id]['draft_notified'] = match_id

        # Handle game start transition
        if transition and transition['current_state'] == 'game_start':
            logger.info(f"Game start detected for user {user_id} in match {match_id}")

            # Get precise start time (current time minus clock_time)
            precise_start_time = int(datetime.now().timestamp())
            if 'map' in data and 'clock_time' in data['map']:
                try:
                    clock_seconds = max(0, int(data['map']['clock_time']))
                    precise_start_time -= clock_seconds
                except (ValueError, TypeError):
                    pass

            # Update database with precise start time
            with get_db_connection() as conn:
                # Check if we're already tracking this match
                existing = conn.execute(
                    'SELECT 1 FROM active_players WHERE user_id = ? AND match_id = ?',
                    (user_id, match_id)
                ).fetchone()

                if existing:
                    conn.execute(
                        'UPDATE active_players SET game_start_time = ? WHERE user_id = ? AND match_id = ?',
                        (precise_start_time, user_id, match_id)
                    )
                    conn.commit()

            # Perform cross-validation
            high_confidence = await cross_validate_match_detection(bot, user_id, match_id, 'gsi')

            # Determine player's team
            player_team = None
            if 'player' in data:
                player_data = data['player']
                player_team = 'team1' if player_data.get('team_name', '').lower() == 'radiant' else 'team2'

            # Only process if we have team info
            if player_team:
                # Make sure there's an entry in active_players
                with get_db_connection() as conn:
                    existing = conn.execute(
                        'SELECT match_start_time FROM active_players WHERE user_id = ? AND match_id = ?',
                        (user_id, match_id)
                    ).fetchone()

                    current_time = int(datetime.now().timestamp())

                    if not existing:
                        conn.execute(
                            'INSERT INTO active_players (user_id, game_id, match_id, team, match_start_time, game_start_time, detection_source) VALUES (?, ?, ?, ?, ?, ?, ?)',
                            (user_id, '570', match_id, player_team, current_time, precise_start_time, 'gsi')
                        )
                        conn.commit()

                        # Update cache
                        from bot.bot import active_players_lock
                        with active_players_lock:
                            bot.active_players_cache[user_id] = {
                                'game_id': '570',
                                'match_id': match_id,
                                'team': player_team,
                                'match_start_time': precise_start_time,
                                'last_check_time': current_time
                            }

                        # Send notification only if this is a new detection or high confidence
                        from utils.notifications import send_match_notification
                        await send_match_notification(bot, user_id, match_id, player_team, "Public Match")

        # Process other game events (keep your existing code)
        if 'events' in data:
            events = data['events']

            # First blood event
            if events.get('first_blood') and not events.get('first_blood_claimed', False):
                # Process first blood (keep your existing code)
                pass

            # Game end event
            if game_state == 'postgame':
                # Process game end (keep your existing code)
                pass

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


def detect_game_phases(data, user_id, bot):
    """Detect key game phases with precise timestamps."""
    if 'map' not in data or not user_id:
        return None

    match_id = data.get('map', {}).get('matchid')
    current_state = data.get('map', {}).get('game_state')

    if not match_id or not current_state:
        return None

    # Get previous state from cache
    previous_state = bot.game_state_cache.get(user_id, {}).get('state')
    current_time = int(datetime.now().timestamp())

    # Check for state transition
    if previous_state != current_state:
        logger.info(f"Game state transition for user {user_id}: {previous_state} → {current_state}")

        # Record transition in database
        with get_db_connection() as conn:
            conn.execute(
                'INSERT INTO game_state_transitions (user_id, match_id, previous_state, new_state, timestamp) VALUES (?, ?, ?, ?, ?)',
                (user_id, match_id, previous_state, current_state, current_time)
            )
            conn.commit()

        # Update cache with new state
        bot.game_state_cache[user_id] = {
            'state': current_state,
            'match_id': match_id,
            'timestamp': current_time
        }

        # Return transition info
        return {
            'match_id': match_id,
            'previous_state': previous_state,
            'current_state': current_state,
            'timestamp': current_time
        }

    # Update timestamp even if no transition
    if user_id in bot.game_state_cache:
        bot.game_state_cache[user_id]['timestamp'] = current_time

    return None


async def cross_validate_match_detection(bot, user_id, match_id, source):
    """Cross-validate match detection from multiple sources."""
    current_time = int(datetime.now().timestamp())

    # Initialize confidence tracking if needed
    if user_id not in bot.match_detection_confidence:
        bot.match_detection_confidence[user_id] = {
            'api_detected': False,
            'gsi_detected': False,
            'draft_detected': False,
            'first_detection': current_time,
            'confidence': 0,
            'match_id': match_id
        }

    # Update detection sources
    if source == 'api':
        bot.match_detection_confidence[user_id]['api_detected'] = True
    elif source == 'gsi':
        bot.match_detection_confidence[user_id]['gsi_detected'] = True
    elif source == 'draft':
        bot.match_detection_confidence[user_id]['draft_detected'] = True

    # Calculate confidence score
    confidence = 0
    if bot.match_detection_confidence[user_id]['api_detected']:
        confidence += 40  # API detection adds 40% confidence
    if bot.match_detection_confidence[user_id]['gsi_detected']:
        confidence += 40  # GSI detection adds 40% confidence
    if bot.match_detection_confidence[user_id]['draft_detected']:
        confidence += 20  # Draft detection adds 20% confidence

    bot.match_detection_confidence[user_id]['confidence'] = confidence

    # Check if high confidence threshold reached
    from config import MATCH_DETECTION_CONFIDENCE_THRESHOLD
    is_high_confidence = confidence >= MATCH_DETECTION_CONFIDENCE_THRESHOLD

    # Record validation data in database
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE active_players SET detection_confidence = ?, validated_at = ? WHERE user_id = ? AND match_id = ?',
            (confidence, current_time, user_id, match_id)
        )
        conn.commit()

    return is_high_confidence