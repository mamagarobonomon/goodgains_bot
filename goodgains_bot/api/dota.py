import requests
import logging
import asyncio
from config import STEAM_API_KEY
from api.rate_limiter import ApiRateLimiter

logger = logging.getLogger('goodgains_bot')
rate_limiter = ApiRateLimiter()


async def get_match_details(match_id):
    """Get details for a specific Dota 2 match."""
    # Check if we should skip this API call due to previous failures
    if not rate_limiter.should_retry(f"match_details_{match_id}"):
        logger.info(f"Skipping API call for match {match_id} due to recent failures")
        return None

    url = f"https://api.steampowered.com/IDOTA2Match_570/GetMatchDetails/v1/?key={STEAM_API_KEY}&match_id={match_id}"
    try:
        async with asyncio.timeout(10):
            response = await asyncio.to_thread(requests.get, url)

            if response.status_code == 500:
                # 500 status typically means match is in progress
                backoff = rate_limiter.record_failure(f"match_details_{match_id}")
                logger.warning(f"API returned 500 for match {match_id}, backing off for {backoff} seconds")
                return {"status": "in_progress"}

            response.raise_for_status()
            data = response.json()

            # Record success to reset backoff
            rate_limiter.record_success(f"match_details_{match_id}")

            if "result" in data:
                # If radiant_win is present, match is complete
                if "radiant_win" in data["result"]:
                    winner = "team1" if data["result"]["radiant_win"] else "team2"
                    return {
                        "status": "completed",
                        "winner": winner,
                        "data": data["result"]
                    }
                else:
                    # Match data exists but no winner yet
                    return {"status": "in_progress", "data": data["result"]}
            else:
                logger.warning(f"Match {match_id} data incomplete")
                return None

    except requests.HTTPError as e:
        backoff = rate_limiter.record_failure(f"match_details_{match_id}")
        logger.error(f"HTTP error fetching match {match_id}: {e}, backing off for {backoff} seconds")
        return None
    except Exception as e:
        logger.error(f"Error fetching match {match_id}: {e}")
        return None


async def get_match_history(account_id, matches_requested=5):
    """Get recent match history for a player."""
    if not rate_limiter.should_retry(f"match_history_{account_id}"):
        logger.info(f"Skipping match history API call for account {account_id} due to rate limiting")
        return None

    url = f"https://api.steampowered.com/IDOTA2Match_570/GetMatchHistory/v1/?key={STEAM_API_KEY}&account_id={account_id}&matches_requested={matches_requested}"
    try:
        response = await asyncio.to_thread(requests.get, url, timeout=10)
        response.raise_for_status()
        data = response.json()

        rate_limiter.record_success(f"match_history_{account_id}")

        if "result" in data and data["result"].get("status") == 1:
            return data["result"].get("matches", [])
        return []
    except Exception as e:
        backoff = rate_limiter.record_failure(f"match_history_{account_id}")
        logger.error(f"Error fetching match history for {account_id}: {e}, backing off for {backoff}s")
        return None


async def get_live_league_games():
    """Get currently active league games."""
    if not rate_limiter.should_retry("live_league_games"):
        return None

    url = f"https://api.steampowered.com/IDOTA2Match_570/GetLiveLeagueGames/v1/?key={STEAM_API_KEY}"
    try:
        response = await asyncio.to_thread(requests.get, url, timeout=8)
        response.raise_for_status()
        data = response.json()

        rate_limiter.record_success("live_league_games")

        if "result" in data and "games" in data["result"]:
            return data["result"]["games"]
        return []
    except Exception as e:
        backoff = rate_limiter.record_failure("live_league_games")
        logger.error(f"Error fetching live league games: {e}, backing off for {backoff}s")
        return None

# Add other Dota 2 API functions as needed