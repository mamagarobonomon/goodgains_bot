import sqlite3
from contextlib import contextmanager
from config import DB_PATH


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def initialize_database():
    """Create necessary tables if they don't exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Steam ID mapping table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS steam_mappings (
            user_id INTEGER PRIMARY KEY,
            steam_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Active players table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_players (
            user_id INTEGER PRIMARY KEY,
            game_id TEXT NOT NULL,
            match_id TEXT NOT NULL,
            team TEXT NOT NULL,
            match_start_time INTEGER NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Bets table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            bet_type TEXT NOT NULL DEFAULT 'team_win',
            team TEXT,
            target TEXT,
            amount REAL NOT NULL,
            placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved BOOLEAN DEFAULT FALSE,
            won BOOLEAN DEFAULT FALSE,
            payout REAL DEFAULT 0,
            tx_hash TEXT
        )
        ''')

        # Match events table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS match_events (
            match_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_target TEXT,
            event_time INTEGER,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (match_id, event_type)
        )
        ''')

        # Wallet sessions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallet_sessions (
            user_id INTEGER PRIMARY KEY,
            wallet_address TEXT,
            session_id TEXT UNIQUE,
            connected BOOLEAN DEFAULT FALSE,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Rate limiting table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS rate_limits (
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, action)
        )
        ''')

        # GSI connections table (if needed)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS gsi_connections (
            user_id INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, timestamp)
        )
        ''')

        conn.commit()