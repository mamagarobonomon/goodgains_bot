import logging
import json

logger = logging.getLogger('goodgains_bot')


def parse_dota2_gsi(data):
    """Parse Dota 2 GSI data into a structured format."""
    try:
        parsed_data = {
            'match_id': None,
            'game_state': None,
            'duration': None,
            'time': None,
            'player': None,
            'team': None,
            'events': [],
            'game_info': {}
        }

        # Extract basic match information
        if 'map' in data:
            map_data = data['map']
            parsed_data['match_id'] = map_data.get('matchid')
            parsed_data['game_state'] = map_data.get('game_state')
            parsed_data['duration'] = map_data.get('game_time')
            parsed_data['time'] = map_data.get('clock_time')

            # Game winner
            if 'win_team' in map_data:
                winner = map_data['win_team'].lower()
                parsed_data['game_info']['winner'] = 'team1' if winner == 'radiant' else 'team2'

        # Extract player information
        if 'player' in data:
            player_data = data['player']
            parsed_data['player'] = {
                'name': player_data.get('name'),
                'hero': player_data.get('hero_name'),
                'kills': player_data.get('kills', 0),
                'deaths': player_data.get('deaths', 0),
                'assists': player_data.get('assists', 0),
                'gold': player_data.get('gold', 0),
                'level': player_data.get('level', 0)
            }

            # Determine team
            if 'team_name' in player_data:
                parsed_data['team'] = 'team1' if player_data['team_name'].lower() == 'radiant' else 'team2'

        # Extract events
        if 'events' in data:
            events_data = data['events']

            # First blood
            if 'first_blood' in events_data:
                parsed_data['events'].append({
                    'type': 'first_blood',
                    'player': events_data.get('first_blood_player', 'Unknown')
                })

            # Aegis pickup
            if 'aegis' in events_data:
                parsed_data['events'].append({
                    'type': 'aegis',
                    'player': events_data.get('aegis_player', 'Unknown')
                })

            # Roshan killed
            if 'roshan' in events_data:
                parsed_data['events'].append({
                    'type': 'roshan'
                })

        # Extract all players data if available
        if 'players' in data:
            parsed_data['game_info']['players'] = []
            players_data = data['players']

            for player_id, player_info in players_data.items():
                if isinstance(player_info, dict):
                    player = {
                        'id': player_id,
                        'name': player_info.get('name', f'Player_{player_id}'),
                        'team': 'team1' if player_info.get('team_name', '').lower() == 'radiant' else 'team2',
                        'hero': player_info.get('hero_name', 'Unknown'),
                        'kills': player_info.get('kills', 0),
                        'deaths': player_info.get('deaths', 0),
                        'assists': player_info.get('assists', 0),
                        'level': player_info.get('level', 0),
                        'net_worth': player_info.get('net_worth', 0),
                        'gpm': player_info.get('gpm', 0),
                        'xpm': player_info.get('xpm', 0)
                    }
                    parsed_data['game_info']['players'].append(player)

        return parsed_data
    except Exception as e:
        logger.error(f"Error parsing GSI data: {e}")
        return None


def generate_gsi_config(user_id, endpoint_url):
    """Generate GSI config file content for a specific user."""
    config = {
        "uri": f"{endpoint_url}/gsi/dota2",
        "timeout": 5.0,
        "buffer": 0.1,
        "throttle": 0.1,
        "heartbeat": 30.0,
        "data": {
            "provider": 1,
            "map": 1,
            "player": 1,
            "hero": 1,
            "abilities": 1,
            "items": 1,
            "draft": 1,
            "wearables": 1,
            "events": 1,
        },
        "auth": {
            "token": f"discord{user_id}"  # Token format to identify user
        }
    }

    return json.dumps(config, indent=2)


def handle_ingame_chat_command(message, user_id, match_id):
    """Parse and handle in-game chat commands."""
    # Format: !command [args]
    parts = message.split()
    command = parts[0].lower() if parts else ""

    if command == "!bet":
        if len(parts) < 3:
            return {"error": "Invalid bet format. Use: !bet amount type [target]"}

        try:
            amount = float(parts[1])
            bet_type = parts[2].lower()

            # Handle team win bet
            if bet_type == "team":
                return {
                    "command": "bet",
                    "bet_type": "team_win",
                    "amount": amount,
                    "user_id": user_id,
                    "match_id": match_id
                }

            # Handle first blood bet
            elif bet_type == "fb" or bet_type == "firstblood":
                if len(parts) < 4:
                    return {"error": "Missing target player. Format: !bet amount fb player_name"}

                target = parts[3]
                return {
                    "command": "bet",
                    "bet_type": "first_blood",
                    "amount": amount,
                    "target": target,
                    "user_id": user_id,
                    "match_id": match_id
                }

            # Handle MVP bet
            elif bet_type == "mvp":
                if len(parts) < 4:
                    return {"error": "Missing target player. Format: !bet amount mvp player_name"}

                target = parts[3]
                return {
                    "command": "bet",
                    "bet_type": "mvp",
                    "amount": amount,
                    "target": target,
                    "user_id": user_id,
                    "match_id": match_id
                }

            else:
                return {"error": "Invalid bet type. Available types: team, fb (firstblood), mvp"}

        except (ValueError, IndexError):
            return {"error": "Invalid bet amount or type."}

    elif command == "!balance":
        return {
            "command": "balance",
            "user_id": user_id
        }

    elif command == "!help":
        return {
            "command": "help",
            "user_id": user_id
        }

    return {"error": "Unknown command"}