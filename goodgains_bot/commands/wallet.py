import discord
from discord import app_commands
import qrcode
import secrets
from io import BytesIO
import asyncio
from datetime import datetime
import logging
from database.connection import get_db_connection
from wallet.walletconnect import create_wallet_session, wait_for_wallet_connection, cleanup_failed_sessions
from wallet.crypto import validate_eth_address

logger = logging.getLogger('goodgains_bot')


def register_commands(bot):
    """Register wallet-related commands."""

    @bot.tree.command(name="connect_wallet", description="Connect your Ethereum wallet using WalletConnect")
    async def connect_wallet(interaction: discord.Interaction):
        """Generate a WalletConnect session link."""
        user_id = interaction.user.id
        logger.info(f"Starting /connect_wallet command for user {user_id}")

        # First, acknowledge the interaction to avoid timeout
        await interaction.response.defer(ephemeral=True)

        # Check rate limits
        with get_db_connection() as conn:
            last_attempt = conn.execute(
                'SELECT timestamp FROM rate_limits WHERE user_id = ? AND action = "connect_wallet"',
                (user_id,)
            ).fetchone()

            if last_attempt:
                last_time = datetime.fromisoformat(last_attempt['timestamp'])
                if (datetime.now() - last_time).total_seconds() < 60:  # 1 minute cooldown
                    await interaction.followup.send("⚠️ Please wait before trying to connect your wallet again.")
                    return

            # Update rate limit
            conn.execute(
                'INSERT OR REPLACE INTO rate_limits (user_id, action, timestamp) VALUES (?, ?, ?)',
                (user_id, "connect_wallet", datetime.now().isoformat())
            )
            conn.commit()

        # Create wallet session
        session = await create_wallet_session(user_id)

        if session:
            # Generate QR code for the WalletConnect URI
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(session['uri'])
            qr.make(fit=True)

            # Create an image from the QR Code
            img = qr.make_image(fill_color="black", back_color="white")

            # Save to BytesIO object
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            # Create a discord.File object from the buffer
            qr_file = discord.File(buffer, filename="walletconnect_qr.png")

            # Send QR code and connection instructions
            await interaction.followup.send(
                f"{interaction.user.mention}, connect your wallet by following these steps:\n\n"
                f"1. **Open your wallet app** (MetaMask, Trust Wallet, etc.)\n"
                f"2. Find the **WalletConnect** or **Scan** option in your wallet app\n"
                f"3. Scan this QR code or manually enter the code:\n"
                f"`{session['uri']}`\n\n"
                f"**IMPORTANT**: Do NOT scan with your phone's camera app - use your wallet app's scanner!\n\n"
                f"Please connect within 60 seconds.",
                file=qr_file
            )

            # Wait for connection event
            connected, wallet_address = await wait_for_wallet_connection(user_id, session['session_id'])

            # Handle connection result
            if connected:
                await interaction.followup.send(
                    f"✅ {interaction.user.mention}, wallet successfully connected: `{wallet_address}`")
                logger.info(f"User {user_id} connected wallet {wallet_address}")

                # Update bot's cache
                from bot.bot import sessions_lock
                with sessions_lock:
                    bot.wallet_sessions_cache[user_id] = {
                        'address': wallet_address,
                        'session_id': session['session_id'],
                        'connected': True
                    }
            else:
                await interaction.followup.send(
                    f"❌ {interaction.user.mention}, wallet connection timed out or failed. Please try again.")
                logger.warning(f"Wallet connection timed out for user {user_id}")

                # Clean up failed session
                cleanup_failed_sessions(user_id)
        else:
            await interaction.followup.send(f"❌ Failed to generate WalletConnect session. Please try again later.")

    @bot.tree.command(name="connect_wallet_direct", description="Connect your wallet by directly entering your address")
    @app_commands.describe(wallet_address="Your Ethereum wallet address (0x...)")
    async def connect_wallet_direct(interaction: discord.Interaction, wallet_address: str):
        """Directly connect a wallet without using WalletConnect."""
        user_id = interaction.user.id

        # Validate wallet address format
        if not validate_eth_address(wallet_address):
            await interaction.response.send_message("❌ Invalid Ethereum address format.", ephemeral=True)
            return

        logger.info(f"User {user_id} starting direct wallet connection for address {wallet_address}")

        # Create a new wallet session
        session_id = f"direct_{user_id}_{int(datetime.now().timestamp())}"

        with get_db_connection() as conn:
            # Check if user already has a connected wallet
            existing = conn.execute(
                'SELECT wallet_address FROM wallet_sessions WHERE user_id = ? AND connected = TRUE',
                (user_id,)
            ).fetchone()

            if existing:
                await interaction.response.send_message(
                    f"⚠️ You already have a connected wallet: `{existing['wallet_address']}`\n"
                    f"Do you want to replace it with `{wallet_address}`? Use `/disconnect_wallet` first.",
                    ephemeral=True
                )
                return

            # Create new wallet connection
            conn.execute(
                'INSERT INTO wallet_sessions (user_id, session_id, wallet_address, connected, last_active) VALUES (?, ?, ?, TRUE, ?)',
                (user_id, session_id, wallet_address, datetime.now().isoformat())
            )
            conn.commit()

        # Update cache
        from bot.bot import sessions_lock
        with sessions_lock:
            bot.wallet_sessions_cache[user_id] = {
                'address': wallet_address,
                'session_id': session_id,
                'connected': True
            }

        await interaction.response.send_message(
            f"✅ Wallet successfully connected!\n\n"
            f"**Address**: `{wallet_address}`\n\n"
            f"You can now place bets with `/bet <amount>`.",
            ephemeral=False
        )
        logger.info(f"User {user_id} directly connected wallet {wallet_address}")

    @bot.tree.command(name="disconnect_wallet", description="Disconnect your current wallet")
    async def disconnect_wallet(interaction: discord.Interaction):
        """Disconnect your currently connected wallet."""
        user_id = interaction.user.id

        with get_db_connection() as conn:
            wallet = conn.execute(
                'SELECT wallet_address FROM wallet_sessions WHERE user_id = ? AND connected = TRUE',
                (user_id,)
            ).fetchone()

            if not wallet:
                await interaction.response.send_message("❌ You don't have a connected wallet.", ephemeral=True)
                return

            # Get the wallet address before disconnecting
            wallet_address = wallet['wallet_address']

            # Disconnect all sessions for this user
            conn.execute(
                'UPDATE wallet_sessions SET connected = FALSE WHERE user_id = ?',
                (user_id,)
            )
            conn.commit()

        # Update cache
        from bot.bot import sessions_lock
        with sessions_lock:
            if user_id in bot.wallet_sessions_cache:
                del bot.wallet_sessions_cache[user_id]

        await interaction.response.send_message(
            f"✅ Wallet `{wallet_address}` has been disconnected.\n"
            f"Use `/connect_wallet_direct` to connect a new wallet.",
            ephemeral=False
        )
        logger.info(f"User {user_id} disconnected wallet {wallet_address}")

    @bot.tree.command(name="wallet_status", description="Check your connected wallet status")
    async def wallet_status(interaction: discord.Interaction):
        """Check if your wallet is connected and get its address."""
        user_id = interaction.user.id

        with get_db_connection() as conn:
            wallet_session = conn.execute(
                'SELECT wallet_address, connected, last_active FROM wallet_sessions WHERE user_id = ? AND connected = TRUE',
                (user_id,)
            ).fetchone()

        if wallet_session:
            last_active = datetime.fromisoformat(wallet_session['last_active'])
            time_ago = datetime.now() - last_active
            hours = time_ago.total_seconds() / 3600

            await interaction.response.send_message(
                f"✅ **Wallet Connected**\n"
                f"Address: `{wallet_session['wallet_address']}`\n"
                f"Connected: {time_ago.days} days, {int(hours % 24)} hours ago\n\n"
                f"Ready to place bets!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ **No Wallet Connected**\n\n"
                "Please connect your wallet using `/connect_wallet`\n"
                "You need a connected wallet to place bets.",
                ephemeral=True
            )

    @bot.tree.command(name="finish_connection", description="Finish wallet connection if it gets stuck")
    @app_commands.describe(wallet_address="Your Ethereum wallet address from MetaMask (0x...)")
    async def finish_connection(interaction: discord.Interaction, wallet_address: str):
        """Manually finish a wallet connection that got stuck."""
        user_id = interaction.user.id

        # Validate wallet address format
        if not validate_eth_address(wallet_address):
            await interaction.response.send_message("❌ Invalid Ethereum address format.", ephemeral=True)
            return

        # Find the most recent session for this user
        with get_db_connection() as conn:
            # Find any pending session
            session = conn.execute(
                'SELECT session_id FROM wallet_sessions WHERE user_id = ? AND connected = FALSE ORDER BY last_active DESC LIMIT 1',
                (user_id,)
            ).fetchone()

            if session:
                # Complete the pending connection
                conn.execute(
                    'UPDATE wallet_sessions SET wallet_address = ?, connected = TRUE, last_active = ? WHERE user_id = ? AND session_id = ?',
                    (wallet_address, datetime.now().isoformat(), user_id, session['session_id'])
                )
                conn.commit()
                await interaction.response.send_message(
                    f"✅ Connection completed! Wallet `{wallet_address}` is now connected.", ephemeral=False)
            else:
                # Create a new connection
                session_id = f"manual_{user_id}_{int(datetime.now().timestamp())}"
                conn.execute(
                    'INSERT INTO wallet_sessions (user_id, session_id, wallet_address, connected, last_active) VALUES (?, ?, ?, TRUE, ?)',
                    (user_id, session_id, wallet_address, datetime.now().isoformat())
                )
                conn.commit()
                await interaction.response.send_message(f"✅ New wallet connection created for `{wallet_address}`",
                                                        ephemeral=False)

        # Update cache
        from bot.bot import sessions_lock
        with sessions_lock:
            bot.wallet_sessions_cache[user_id] = {
                'address': wallet_address,
                'session_id': session[
                    'session_id'] if session else f"manual_{user_id}_{int(datetime.now().timestamp())}",
                'connected': True
            }

    logger.info("Wallet commands registered")
    return bot