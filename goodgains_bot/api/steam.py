import requests
import logging
import asyncio
from urllib.parse import urlparse
import re
from config import STEAM_API_KEY
from api.rate_limiter import ApiRateLimiter

logger = logging.getLogger('goodgains_bot')
rate_limiter = ApiRateLimiter()


async def get_player_summary(steam_id):
    """Get player summary from Steam API."""
    if not rate_limiter.should_retry(f"player_summary_{steam_id}"):
        logger.info(f"Skipping API call for player {steam_id} due to rate limiting")
        return None

    url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={STEAM_API_KEY}&steamids={steam_id}"
    try:
        async with asyncio.timeout(10):
            response = await asyncio.to_thread(requests.get, url)
            response.raise_for_status()
            data = response.json()

            rate_limiter.record_success(f"player_summary_{steam_id}")

            if "response" in data and "players" in data["response"]:
                return data["response"]["players"][0] if data["response"]["players"] else None
            return None
    except Exception as e:
        backoff = rate_limiter.record_failure(f"player_summary_{steam_id}")
        logger.error(f"Error fetching player summary for {steam_id}: {e}, backing off for {backoff} seconds")
        return None


async def resolve_vanity_url(vanity_url):
    """Resolve a Steam vanity URL to a Steam ID."""
    if not rate_limiter.should_retry(f"vanity_url_{vanity_url}"):
        return None

    url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/?key={STEAM_API_KEY}&vanityurl={vanity_url}"
    try:
        response = await asyncio.to_thread(requests.get, url)
        response.raise_for_status()
        data = response.json()

        rate_limiter.record_success(f"vanity_url_{vanity_url}")

        if data["response"]["success"] == 1:
            return data["response"]["steamid"]
        return None
    except Exception as e:
        backoff = rate_limiter.record_failure(f"vanity_url_{vanity_url}")
        logger.error(f"Error resolving vanity URL {vanity_url}: {e}, backing off for {backoff} seconds")
        return None


def extract_steam_id_from_url(steam_url):
    """Extract Steam ID from a Steam profile URL."""
    parsed_url = urlparse(steam_url)
    if parsed_url.netloc != "steamcommunity.com":
        return None

    # Extract from /profiles/steamid format
    if "/profiles/" in steam_url:
        steam_id_match = re.search(r"profiles/(\d{17})", steam_url)
        if steam_id_match:
            return steam_id_match.group(1)

    # Extract from /id/customid format
    elif "/id/" in steam_url:
        custom_id_match = re.search(r"id/([^/]+)", steam_url)
        if custom_id_match:
            return custom_id_match.group(1)

    return None


async def check_api_health():
    """Check if the Steam API is working properly."""
    try:
        test_url = f"https://api.steampowered.com/ISteamWebAPIUtil/GetSupportedAPIList/v1/?key={STEAM_API_KEY}"
        async with asyncio.timeout(5):
            response = await asyncio.to_thread(requests.get, test_url)
            response.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Steam API health check failed: {e}")
        return False