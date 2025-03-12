import logging
from datetime import datetime
from database.connection import get_db_connection
from utils.notifications import send_bet_result

logger = logging.getLogger('goodgains_bot')


async def resolve_match_team_win_bets(bot, match_id, winning_team):
    """Resolve all team win bets for a given match."""
    logger.info(f"Resolving team win bets for match {match_id} with winner {winning_team}")

    with get_db_connection() as conn:
        # Get all team win bets for this match
        team_bets = conn.execute(
            'SELECT id, user_id, team, amount FROM bets WHERE match_id = ? AND bet_type = "team_win" AND resolved = FALSE',
            (match_id,)
        ).fetchall()

        if not team_bets:
            logger.info(f"No unresolved team win bets found for match {match_id}")
            return

        for bet in team_bets:
            # Determine if bet won
            won = bet['team'] == winning_team

            # Calculate payout (2x for winning, 0 for losing)
            payout = bet['amount'] * 2 if won else 0

            # Update bet record
            conn.execute(
                'UPDATE bets SET resolved = TRUE, won = ?, payout = ? WHERE id = ?',
                (won, payout, bet['id'])
            )

            # Notify user of result
            await send_bet_result(
                bot,
                bet['user_id'],
                "team_win",
                match_id,
                won,
                bet['amount'],
                payout,
                team=bet['team'],
                actual_result=winning_team
            )

        conn.commit()

    logger.info(f"Resolved {len(team_bets)} team win bets for match {match_id}")


async def resolve_first_blood_bets(bot, match_id, first_blood_player):
    """Resolve all first blood bets for a given match."""
    logger.info(f"Resolving first blood bets for match {match_id} with player {first_blood_player}")

    with get_db_connection() as conn:
        # Get all first blood bets for this match
        fb_bets = conn.execute(
            'SELECT id, user_id, target, amount FROM bets WHERE match_id = ? AND bet_type = "first_blood" AND resolved = FALSE',
            (match_id,)
        ).fetchall()

        if not fb_bets:
            logger.info(f"No unresolved first blood bets found for match {match_id}")
            return

        for bet in fb_bets:
            # Case-insensitive comparison for player names
            won = bet['target'].lower() == first_blood_player.lower()

            # Calculate payout (2x for winning, 0 for losing)
            payout = bet['amount'] * 2 if won else 0

            # Update bet record
            conn.execute(
                'UPDATE bets SET resolved = TRUE, won = ?, payout = ? WHERE id = ?',
                (won, payout, bet['id'])
            )

            # Notify user of result
            await send_bet_result(
                bot,
                bet['user_id'],
                "first_blood",
                match_id,
                won,
                bet['amount'],
                payout,
                target=bet['target'],
                actual_result=first_blood_player
            )

        conn.commit()

    logger.info(f"Resolved {len(fb_bets)} first blood bets for match {match_id}")


async def resolve_mvp_bets(bot, match_id, mvp_player):
    """Resolve all MVP bets for a given match."""
    logger.info(f"Resolving MVP bets for match {match_id} with player {mvp_player}")

    with get_db_connection() as conn:
        # Get all MVP bets for this match
        mvp_bets = conn.execute(
            'SELECT id, user_id, target, amount FROM bets WHERE match_id = ? AND bet_type = "mvp" AND resolved = FALSE',
            (match_id,)
        ).fetchall()

        if not mvp_bets:
            logger.info(f"No unresolved MVP bets found for match {match_id}")
            return

        for bet in mvp_bets:
            # Case-insensitive comparison for player names
            won = bet['target'].lower() == mvp_player.lower()

            # Calculate payout (3x for winning MVP bet, 0 for losing)
            payout = bet['amount'] * 3 if won else 0

            # Update bet record
            conn.execute(
                'UPDATE bets SET resolved = TRUE, won = ?, payout = ? WHERE id = ?',
                (won, payout, bet['id'])
            )

            # Notify user of result
            await send_bet_result(
                bot,
                bet['user_id'],
                "mvp",
                match_id,
                won,
                bet['amount'],
                payout,
                target=bet['target'],
                actual_result=mvp_player
            )

        conn.commit()

    logger.info(f"Resolved {len(mvp_bets)} MVP bets for match {match_id}")


async def check_event_based_bets(bot, match_id):
    """Check for event-based bets ready for resolution."""
    with get_db_connection() as conn:
        # Get events recorded for this match
        events = conn.execute(
            'SELECT event_type, event_target FROM match_events WHERE match_id = ?',
            (match_id,)
        ).fetchall()

        if not events:
            return

        # Create a dict of events for easier access
        event_dict = {event['event_type']: event['event_target'] for event in events}

        # Resolve First Blood bets if event exists
        if "first_blood" in event_dict:
            first_blood_player = event_dict["first_blood"]
            await resolve_first_blood_bets(bot, match_id, first_blood_player)

        # Resolve MVP bets if event exists
        if "mvp" in event_dict:
            mvp_player = event_dict["mvp"]
            await resolve_mvp_bets(bot, match_id, mvp_player)


async def track_betting_streak(bot, user_id):
    """Track and notify users about betting streaks."""
    with get_db_connection() as conn:
        # Get recent bets in chronological order
        recent_bets = conn.execute(
            '''SELECT match_id, won, placed_at
            FROM bets 
            WHERE user_id = ? AND resolved = TRUE
            ORDER BY placed_at DESC
            LIMIT 10''',
            (user_id,)
        ).fetchall()

    # Calculate current streak
    streak_type = None
    streak_count = 0

    for bet in recent_bets:
        if streak_type is None:
            streak_type = bet['won']
            streak_count = 1
        elif bet['won'] == streak_type:
            streak_count += 1
        else:
            break

    # Send notifications for significant streaks (3 or more)
    if streak_count >= 3:
        streak_message = (
            f"🔥 **Betting Streak Alert!**\n\n"
            f"You're on a **{streak_count}** bet "
            f"{'winning' if streak_type else 'losing'} streak!\n\n"
        )

        if streak_type:  # Winning streak
            streak_message += (
                f"You're on fire! Keep up the good predictions.\n"
                f"Consider gradually increasing your bet sizes to maximize your profits!"
            )
        else:  # Losing streak
            streak_message += (
                f"Looks like a rough patch. Consider these tips:\n"
                f"• Take a short break to reset\n"
                f"• Reduce your bet sizes temporarily\n"
                f"• Try different bet types that match your strengths"
            )

        await bot.send_direct_message(user_id, streak_message)
        logger.info(f"Notified user {user_id} of {streak_count} bet {'winning' if streak_type else 'losing'} streak")