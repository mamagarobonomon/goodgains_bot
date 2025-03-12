import logging
import discord
from datetime import datetime

logger = logging.getLogger('goodgains_bot')


async def send_match_notification(bot, user_id, match_id, team, match_type):
    """Send match start notification to user and log channel."""
    log_channel = bot.get_channel(bot.log_channel_id)

    # Channel notification
    try:
        if log_channel:
            await log_channel.send(
                f"🎮 <@{user_id}>, you're now playing Dota 2 ({match_type}) on {team} in match {match_id}! "
                f"You have 5 minutes to place bets using `/bet <amount>`."
            )
            logger.info(f"Sent match notification to channel for user {user_id}")
        else:
            logger.error(f"Could not find log channel with ID {bot.log_channel_id}")
    except Exception as e:
        logger.error(f"Failed to send match notification to channel: {e}")

    # Direct message notification
    bet_message = (
        f"🎮 **Dota 2 Match Detected!**\n\n"
        f"You're now playing in match **{match_id}** on **{team}**.\n\n"
        f"**⏰ BETTING WINDOW OPEN FOR 5 MINUTES! ⏰**\n\n"
        f"**Available Bet Types:**\n"
        f"1️⃣ `/bet [amount]` - Bet on your team winning\n"
        f"2️⃣ `/bet_first_blood [player] [amount]` - Bet on who gets First Blood\n"
        f"3️⃣ `/bet_mvp [player] [amount]` - Bet on the match MVP\n\n"
        f"**Quick Example:** `/bet 0.1` to bet 0.1 ETH on your team winning\n\n"
        f"Good luck! 🍀"
    )
    await bot.send_direct_message(user_id, bet_message)


async def send_bet_confirmation(bot, user_id, bet_type, amount, match_id, team=None, target=None):
    """Send bet confirmation to user."""
    # Format message based on bet type
    if bet_type == "team_win":
        dm_message = (
            f"🎮 **Bet Confirmation**\n\n"
            f"You've successfully placed a bet of **{amount} ETH** on **{team}** in match **{match_id}**.\n"
            f"Game: Dota 2\n"
            f"This bet is in testing mode, no actual crypto has been transferred.\n\n"
            f"Good luck! We'll notify you of the results after the match ends."
        )
    elif bet_type == "first_blood":
        dm_message = (
            f"🎮 **Bet Confirmation: First Blood**\n\n"
            f"You've successfully placed a bet of **{amount} ETH** that **{target}** will get First Blood in match **{match_id}**.\n"
            f"Game: Dota 2\n"
            f"This bet is in testing mode, no actual crypto has been transferred.\n\n"
            f"Good luck! We'll notify you of the results after the match ends."
        )
    elif bet_type == "mvp":
        dm_message = (
            f"🎮 **Bet Confirmation: MVP Prediction**\n\n"
            f"You've successfully placed a bet of **{amount} ETH** that **{target}** will be MVP in match **{match_id}**.\n"
            f"Game: Dota 2\n"
            f"This bet is in testing mode, no actual crypto has been transferred.\n\n"
            f"Good luck! We'll notify you of the results after the match ends."
        )
    else:
        dm_message = (
            f"🎮 **Bet Confirmation**\n\n"
            f"You've successfully placed a bet of **{amount} ETH** in match **{match_id}**.\n"
            f"Bet type: {bet_type}\n"
            f"This bet is in testing mode, no actual crypto has been transferred.\n\n"
            f"Good luck! We'll notify you of the results after the match ends."
        )

    await bot.send_direct_message(user_id, dm_message)

    # Notify log channel
    log_channel = bot.get_channel(bot.log_channel_id)
    if log_channel:
        if bet_type == "team_win":
            await log_channel.send(
                f"💰 <@{user_id}> placed a {amount} ETH bet on {team} in match {match_id}!"
            )
        elif bet_type == "first_blood":
            await log_channel.send(
                f"💰 <@{user_id}> placed a {amount} ETH bet on {target} getting First Blood in match {match_id}!"
            )
        elif bet_type == "mvp":
            await log_channel.send(
                f"💰 <@{user_id}> placed a {amount} ETH bet on {target} being MVP in match {match_id}!"
            )


async def send_bet_result(bot, user_id, bet_type, match_id, won, amount, payout, team=None, target=None,
                          actual_result=None):
    """Send bet result notification to user."""
    if bet_type == "team_win":
        if won:
            dm_message = (
                f"🏆 **Team Win Bet Won!**\n\n"
                f"Congratulations! Your team **{team}** won the match!\n"
                f"Match: {match_id}\n"
                f"Your Bet: {amount:.4f} ETH\n"
                f"Your Winnings: {payout:.4f} ETH\n\n"
                f"_(Testing mode: no actual crypto transferred)_"
            )
        else:
            dm_message = (
                f"❌ **Team Win Bet Lost**\n\n"
                f"Unfortunately, your team **{team}** lost the match.\n"
                f"The winning team was: **{actual_result}**\n"
                f"Match: {match_id}\n"
                f"Your Bet: {amount:.4f} ETH\n\n"
                f"Better luck next time!\n"
                f"_(Testing mode: no actual crypto transferred)_"
            )
    elif bet_type == "first_blood":
        if won:
            dm_message = (
                f"🏆 **First Blood Bet Won!**\n\n"
                f"Congratulations! Your bet that **{target}** would get First Blood was correct!\n"
                f"Match: {match_id}\n"
                f"Your Bet: {amount:.4f} ETH\n"
                f"Your Winnings: {payout:.4f} ETH\n\n"
                f"_(Testing mode: no actual crypto transferred)_"
            )
        else:
            dm_message = (
                f"❌ **First Blood Bet Lost**\n\n"
                f"Your bet that **{target}** would get First Blood was incorrect.\n"
                f"The actual First Blood was by: **{actual_result}**\n"
                f"Match: {match_id}\n"
                f"Your Bet: {amount:.4f} ETH\n\n"
                f"Better luck next time!\n"
                f"_(Testing mode: no actual crypto transferred)_"
            )
    elif bet_type == "mvp":
        if won:
            dm_message = (
                f"🏆 **MVP Bet Won!**\n\n"
                f"Congratulations! Your bet that **{target}** would be MVP was correct!\n"
                f"Match: {match_id}\n"
                f"Your Bet: {amount:.4f} ETH\n"
                f"Your Winnings: {payout:.4f} ETH\n\n"
                f"_(Testing mode: no actual crypto transferred)_"
            )
        else:
            dm_message = (
                f"❌ **MVP Bet Lost**\n\n"
                f"Your bet that **{target}** would be MVP was incorrect.\n"
                f"The actual MVP was: **{actual_result}**\n"
                f"Match: {match_id}\n"
                f"Your Bet: {amount:.4f} ETH\n\n"
                f"Better luck next time!\n"
                f"_(Testing mode: no actual crypto transferred)_"
            )

    await bot.send_direct_message(user_id, dm_message)

    # Notify log channel if bet was won
    if won:
        log_channel = bot.get_channel(bot.log_channel_id)
        if log_channel:
            if bet_type == "team_win":
                await log_channel.send(
                    f"🎉 <@{user_id}> won {payout:.4f} ETH betting on {team} in match {match_id}!"
                )
            elif bet_type == "first_blood":
                await log_channel.send(
                    f"🎉 <@{user_id}> won {payout:.4f} ETH betting on {target} getting First Blood!"
                )
            elif bet_type == "mvp":
                await log_channel.send(
                    f"🎉 <@{user_id}> won {payout:.4f} ETH betting on {target} being MVP!"
                )