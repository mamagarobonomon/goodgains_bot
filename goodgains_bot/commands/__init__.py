from discord.ext import commands


def register_all_commands(bot):
    """Register all slash commands with the bot."""
    # Import command modules
    from commands import general, betting, wallet, profile, admin

    # Register commands
    general.register_commands(bot)
    betting.register_commands(bot)
    wallet.register_commands(bot)
    profile.register_commands(bot)
    admin.register_commands(bot)

    return bot