import logging
from datetime import datetime
from database.connection import get_db_connection

logger = logging.getLogger('goodgains_bot')


async def register_events(bot):
    """Register event handlers."""

    # Define event handlers here to avoid circular imports

    @bot.event
    async def on_message(message):
        # Don't respond to bot's own messages
        if message.author == bot.user:
            return

        # Process commands
        await bot.process_commands(message)

        # Check for possible direct instructions from users
        if message.guild is None:  # DM channel
            # Handle certain keywords
            content = message.content.lower()

            # Help request
            if content == 'help' or content == '!help':
                await message.author.send(
                    "**GoodGains Bot Help**\n\n"
                    "Here are the available commands:\n"
                    "• `/link_steam` - Link your Steam account\n"
                    "• `/connect_wallet` - Connect your ETH wallet\n"
                    "• `/bet` - Bet on your team winning\n"
                    "• `/bet_first_blood` - Bet on who gets first blood\n"
                    "• `/bet_mvp` - Bet on match MVP\n"
                    "• `/profile` - View your betting profile\n"
                    "• `/check_match` - Check if you're in an active match\n\n"
                    "For more detailed help on a specific command, use `/help [command]`"
                )

    @bot.event
    async def on_command_error(ctx, error):
        # Handle various Discord.py command errors
        import discord

        if isinstance(error, discord.app_commands.CommandNotFound):
            await ctx.send("Command not found. Use `/help` to see available commands.")

        elif isinstance(error, discord.app_commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: {error.param}")

        elif isinstance(error, discord.app_commands.BadArgument):
            await ctx.send(f"Invalid argument provided: {error}")

        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.2f} seconds.")

        else:
            logger.error(f"Command error: {error}")
            await ctx.send("An error occurred while executing the command.")

    @bot.event
    async def on_disconnect():
        logger.warning("Bot disconnected from Discord.")

    @bot.event
    async def on_resumed():
        logger.info("Bot connection resumed.")

    @bot.event
    async def on_guild_join(guild):
        """Log when the bot joins a new guild."""
        logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")

        # Try to find a suitable channel to send a welcome message
        general_channel = None
        for channel in guild.text_channels:
            if channel.name == 'general' or 'general' in channel.name:
                general_channel = channel
                break

        if general_channel and general_channel.permissions_for(guild.me).send_messages:
            await general_channel.send(
                "👋 **Hello everyone!**\n\n"
                "I'm GoodGains Bot, your assistant for Dota 2 betting!\n\n"
                "To get started:\n"
                "1️⃣ Link your Steam account with `/link_steam`\n"
                "2️⃣ Connect your wallet with `/connect_wallet`\n"
                "3️⃣ Play Dota 2 and place bets with `/bet`\n\n"
                "Type `/help` for more information!"
            )

    logger.info("Event handlers registered")