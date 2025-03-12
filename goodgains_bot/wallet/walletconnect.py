import secrets
import logging
import asyncio
from datetime import datetime
from config import WALLETCONNECT_PROJECT_ID
from database.connection import get_db_connection

logger = logging.getLogger('goodgains_bot')

async def create_wallet_session(user_id):
    """Create a WalletConnect session with proper webhook support for MetaMask."""
    logger.info(f"Initiating WalletConnect session for user {user_id}...")

    if not WALLETCONNECT_PROJECT_ID:
        logger.error("WALLETCONNECT_PROJECT_ID is missing in .env!")
        return None

    # Generate session parameters
    session_id = secrets.token_hex(16)  # Random topic
    session_key = secrets.token_hex(32)  # 256-bit encryption key

    # Build the URI specifically formatted for MetaMask
    # MetaMask expects this exact format for WalletConnect v2
    wc_uri = f"wc:{session_id}@2?relay-protocol=irn&relay-url=relay.walletconnect.com&symKey={session_key}"

    # Add project ID if available
    if WALLETCONNECT_PROJECT_ID:
        wc_uri += f"&projectId={WALLETCONNECT_PROJECT_ID}"

    logger.info(f"WalletConnect URI generated for MetaMask: {wc_uri}")

    try:
        # Save pending session to database
        with get_db_connection() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO wallet_sessions (user_id, session_id, connected) VALUES (?, ?, FALSE)',
                (user_id, session_id)
            )
            conn.commit()

        return {
            "uri": wc_uri,
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"Error during WalletConnect session creation: {e}")
        return None

async def wait_for_wallet_connection(user_id, session_id, timeout=60):
    """Wait for the wallet connection to be established."""
    start_time = datetime.now()
    connected = False
    wallet_address = None

    while (datetime.now() - start_time).total_seconds() < timeout:
        # Check connection status
        with get_db_connection() as conn:
            status = conn.execute(
                'SELECT connected, wallet_address FROM wallet_sessions WHERE user_id = ? AND session_id = ?',
                (user_id, session_id)
            ).fetchone()

            if status and status['connected']:
                connected = True
                wallet_address = status['wallet_address']
                break

        await asyncio.sleep(2)  # Check every 2 seconds

    return connected, wallet_address

def cleanup_failed_sessions(user_id):
    """Clean up failed wallet connection sessions."""
    with get_db_connection() as conn:
        conn.execute(
            'DELETE FROM wallet_sessions WHERE user_id = ? AND connected = FALSE',
            (user_id,)
        )
        conn.commit()