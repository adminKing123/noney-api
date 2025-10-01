import json
import random
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, Counter
from google.genai import types

# Load DB
with open("relation-data.json", "r", encoding="utf-8") as f:
    DB = json.load(f)


# ==================== FUNCTION IMPLEMENTATIONS ====================

def search_songs(
    query: Optional[str] = None,
    artist_name: Optional[str] = None,
    album_name: Optional[str] = None,
    tag_name: Optional[str] = None,
    min_duration: Optional[int] = None,
    max_duration: Optional[int] = None,
    limit: int = 10
) -> List[Dict]:
    """Search for songs based on various criteria with duration filters."""
    results = []
    
    for song_id, song in DB["songs"].items():
        match = True
        
        if query:
            query_lower = query.lower()
            if query_lower not in song["title"].lower() and query_lower not in song["original_name"].lower():
                match = False
        
        if artist_name and match:
            artist_match = False
            for artist_id in song["artist_ids"]:
                if artist_id in DB["artists"] and artist_name.lower() in DB["artists"][artist_id]["name"].lower():
                    artist_match = True
                    break
            if not artist_match:
                match = False
        
        if album_name and match:
            album_id = song["album_id"]
            if album_id in DB["albums"] and album_name.lower() not in DB["albums"][album_id]["title"].lower():
                match = False
        
        if tag_name and match:
            tag_match = False
            for tag_id in song["tag_ids"]:
                if tag_id in DB["tags"] and tag_name.lower() in DB["tags"][tag_id]["name"].lower():
                    tag_match = True
                    break
            if not tag_match:
                match = False
        
        if min_duration and match:
            if song["duration"] < min_duration:
                match = False
        
        if max_duration and match:
            if song["duration"] > max_duration:
                match = False
        
        if match:
            results.append(song)
        
        if len(results) >= limit:
            break
    
    return results


def get_song_details(song_id: int) -> Optional[Dict]:
    """Get detailed information about a specific song."""
    song_id_str = str(song_id)
    if song_id_str not in DB["songs"]:
        return None
    
    song = DB["songs"][song_id_str].copy()
    
    song["artists"] = [
        DB["artists"][str(aid)] for aid in song["artist_ids"] 
        if str(aid) in DB["artists"]
    ]
    
    if song["album_id"] in DB["albums"]:
        song["album"] = DB["albums"][song["album_id"]]
    
    song["tags"] = [
        DB["tags"][str(tid)] for tid in song["tag_ids"] 
        if str(tid) in DB["tags"]
    ]
    
    return song


def get_artist_info(artist_id: Optional[int] = None, artist_name: Optional[str] = None) -> Optional[Dict]:
    """Get information about an artist and their songs."""
    artist = None
    
    if artist_id:
        artist_id_str = str(artist_id)
        if artist_id_str in DB["artists"]:
            artist = DB["artists"][artist_id_str].copy()
    elif artist_name:
        for aid, a in DB["artists"].items():
            if artist_name.lower() in a["name"].lower():
                artist = a.copy()
                break
    
    if not artist:
        return None
    
    artist["songs"] = [
        DB["songs"][str(sid)] for sid in artist["song_ids"] 
        if str(sid) in DB["songs"]
    ]
    
    return artist


def get_album_info(album_id: Optional[int] = None, album_name: Optional[str] = None) -> Optional[Dict]:
    """Get information about an album and its songs."""
    album = None
    
    if album_id:
        album_id_str = str(album_id)
        if album_id_str in DB["albums"]:
            album = DB["albums"][album_id_str].copy()
    elif album_name:
        for aid, a in DB["albums"].items():
            if album_name.lower() in a["title"].lower():
                album = a.copy()
                break
    
    if not album:
        return None
    
    album["songs"] = [
        DB["songs"][str(sid)] for sid in album["song_ids"] 
        if str(sid) in DB["songs"]
    ]
    
    return album


def get_random_songs(count: int = 5, tag_name: Optional[str] = None) -> List[Dict]:
    """Get random songs, optionally filtered by tag."""
    songs = list(DB["songs"].values())
    
    if tag_name:
        filtered_songs = []
        for song in songs:
            for tag_id in song["tag_ids"]:
                if str(tag_id) in DB["tags"] and tag_name.lower() in DB["tags"][str(tag_id)]["name"].lower():
                    filtered_songs.append(song)
                    break
        songs = filtered_songs
    
    return random.sample(songs, min(count, len(songs)))


def list_all_artists(limit: int = 50) -> List[Dict]:
    """List all artists in the database."""
    artists = list(DB["artists"].values())
    return artists[:limit]


def list_all_albums(year: Optional[int] = None, limit: int = 50) -> List[Dict]:
    """List all albums, optionally filtered by year."""
    albums = list(DB["albums"].values())
    
    if year:
        albums = [a for a in albums if a["year"] == year]
    
    return albums[:limit]


def list_all_tags() -> List[Dict]:
    """List all available tags."""
    return list(DB["tags"].values())


def get_songs_by_year(year: int, limit: int = 20) -> List[Dict]:
    """Get songs from a specific year."""
    results = []
    
    for song in DB["songs"].values():
        album_id = song["album_id"]
        if album_id in DB["albums"] and DB["albums"][album_id]["year"] == year:
            results.append(song)
        
        if len(results) >= limit:
            break
    
    return results


def get_artist_collaborations(artist_id: int) -> List[Dict]:
    """Get songs where the artist collaborated with others."""
    artist_id_str = str(artist_id)
    if artist_id_str not in DB["artists"]:
        return []
    
    collaborations = []
    for song_id in DB["artists"][artist_id_str]["song_ids"]:
        song = DB["songs"][str(song_id)]
        if len(song["artist_ids"]) > 1:
            collaborations.append(song)
    
    return collaborations


def get_top_artists_by_song_count(limit: int = 10) -> List[Dict]:
    """Get artists with the most songs in the database."""
    artist_counts = []
    
    for artist_id, artist in DB["artists"].items():
        artist_counts.append({
            "artist": artist,
            "song_count": len(artist["song_ids"])
        })
    
    artist_counts.sort(key=lambda x: x["song_count"], reverse=True)
    return artist_counts[:limit]


def get_albums_by_decade(decade: int, limit: int = 50) -> List[Dict]:
    """Get albums from a specific decade (e.g., 2010 for 2010-2019)."""
    results = []
    decade_start = decade
    decade_end = decade + 9
    
    for album in DB["albums"].values():
        if decade_start <= album["year"] <= decade_end:
            results.append(album)
        
        if len(results) >= limit:
            break
    
    return results


def get_longest_songs(limit: int = 10, tag_name: Optional[str] = None) -> List[Dict]:
    """Get the longest songs, optionally filtered by tag."""
    songs = list(DB["songs"].values())
    
    if tag_name:
        filtered_songs = []
        for song in songs:
            for tag_id in song["tag_ids"]:
                if str(tag_id) in DB["tags"] and tag_name.lower() in DB["tags"][str(tag_id)]["name"].lower():
                    filtered_songs.append(song)
                    break
        songs = filtered_songs
    
    songs.sort(key=lambda x: x["duration"], reverse=True)
    return songs[:limit]


def get_shortest_songs(limit: int = 10, tag_name: Optional[str] = None) -> List[Dict]:
    """Get the shortest songs, optionally filtered by tag."""
    songs = list(DB["songs"].values())
    
    if tag_name:
        filtered_songs = []
        for song in songs:
            for tag_id in song["tag_ids"]:
                if str(tag_id) in DB["tags"] and tag_name.lower() in DB["tags"][str(tag_id)]["name"].lower():
                    filtered_songs.append(song)
                    break
        songs = filtered_songs
    
    songs.sort(key=lambda x: x["duration"])
    return songs[:limit]


def get_artist_statistics(artist_id: int) -> Optional[Dict]:
    """Get comprehensive statistics about an artist."""
    artist_id_str = str(artist_id)
    if artist_id_str not in DB["artists"]:
        return None
    
    artist = DB["artists"][artist_id_str]
    songs = [DB["songs"][str(sid)] for sid in artist["song_ids"] if str(sid) in DB["songs"]]
    
    if not songs:
        return {
            "artist": artist,
            "total_songs": 0,
            "solo_songs": 0,
            "collaborations": 0,
            "albums": [],
            "total_duration": 0,
            "average_duration": 0
        }
    
    solo_count = sum(1 for s in songs if len(s["artist_ids"]) == 1)
    collab_count = sum(1 for s in songs if len(s["artist_ids"]) > 1)
    
    album_ids = set(s["album_id"] for s in songs)
    albums = [DB["albums"][aid] for aid in album_ids if aid in DB["albums"]]
    
    total_duration = sum(s["duration"] for s in songs)
    avg_duration = total_duration / len(songs)
    
    return {
        "artist": artist,
        "total_songs": len(songs),
        "solo_songs": solo_count,
        "collaborations": collab_count,
        "albums": albums,
        "total_duration": total_duration,
        "average_duration": avg_duration
    }


def get_album_statistics(album_id: int) -> Optional[Dict]:
    """Get comprehensive statistics about an album."""
    album_id_str = str(album_id)
    if album_id_str not in DB["albums"]:
        return None
    
    album = DB["albums"][album_id_str]
    songs = [DB["songs"][str(sid)] for sid in album["song_ids"] if str(sid) in DB["songs"]]
    
    if not songs:
        return {
            "album": album,
            "total_songs": 0,
            "total_duration": 0,
            "average_duration": 0,
            "artists": []
        }
    
    artist_ids = set()
    for song in songs:
        artist_ids.update(song["artist_ids"])
    
    artists = [DB["artists"][str(aid)] for aid in artist_ids if str(aid) in DB["artists"]]
    
    total_duration = sum(s["duration"] for s in songs)
    avg_duration = total_duration / len(songs)
    
    return {
        "album": album,
        "total_songs": len(songs),
        "total_duration": total_duration,
        "average_duration": avg_duration,
        "artists": artists
    }


def search_by_duration_range(min_minutes: int = 0, max_minutes: int = 10, limit: int = 20) -> List[Dict]:
    """Search songs within a specific duration range (in minutes)."""
    min_seconds = min_minutes * 60
    max_seconds = max_minutes * 60
    
    results = []
    for song in DB["songs"].values():
        if min_seconds <= song["duration"] <= max_seconds:
            results.append(song)
        
        if len(results) >= limit:
            break
    
    return results


def get_artist_collaborators(artist_id: int) -> List[Dict]:
    """Get all artists who have collaborated with a specific artist."""
    artist_id_str = str(artist_id)
    if artist_id_str not in DB["artists"]:
        return []
    
    collaborator_ids = set()
    
    for song_id in DB["artists"][artist_id_str]["song_ids"]:
        song = DB["songs"][str(song_id)]
        if len(song["artist_ids"]) > 1:
            for aid in song["artist_ids"]:
                if aid != int(artist_id):
                    collaborator_ids.add(str(aid))
    
    collaborators = [DB["artists"][cid] for cid in collaborator_ids if cid in DB["artists"]]
    return collaborators


def get_songs_by_year_range(start_year: int, end_year: int, limit: int = 50) -> List[Dict]:
    """Get songs from a range of years."""
    results = []
    
    for song in DB["songs"].values():
        album_id = song["album_id"]
        if album_id in DB["albums"]:
            album_year = DB["albums"][album_id]["year"]
            if start_year <= album_year <= end_year:
                results.append(song)
        
        if len(results) >= limit:
            break
    
    return results


def get_multi_artist_songs(min_artists: int = 2, limit: int = 20) -> List[Dict]:
    """Get songs with multiple artists (collaborations)."""
    results = []
    
    for song in DB["songs"].values():
        if len(song["artist_ids"]) >= min_artists:
            results.append(song)
        
        if len(results) >= limit:
            break
    
    return results


def search_songs_fuzzy(query: str, threshold: int = 3, limit: int = 10) -> List[Dict]:
    """Fuzzy search for songs allowing partial matches."""
    results = []
    query_lower = query.lower()
    
    for song in DB["songs"].values():
        title_lower = song["title"].lower()
        original_lower = song["original_name"].lower()
        
        # Check if query words appear in title or original name
        if any(word in title_lower or word in original_lower for word in query_lower.split()):
            results.append(song)
        
        if len(results) >= limit:
            break
    
    return results


def get_database_statistics() -> Dict:
    """Get comprehensive database statistics."""
    total_songs = len(DB["songs"])
    total_artists = len(DB["artists"])
    total_albums = len(DB["albums"])
    total_tags = len(DB["tags"])
    
    total_duration = sum(song["duration"] for song in DB["songs"].values())
    avg_song_duration = total_duration / total_songs if total_songs > 0 else 0
    
    years = [DB["albums"][song["album_id"]]["year"] for song in DB["songs"].values() if song["album_id"] in DB["albums"]]
    oldest_year = min(years) if years else None
    newest_year = max(years) if years else None
    
    collab_count = sum(1 for song in DB["songs"].values() if len(song["artist_ids"]) > 1)
    
    return {
        "total_songs": total_songs,
        "total_artists": total_artists,
        "total_albums": total_albums,
        "total_tags": total_tags,
        "total_duration_seconds": total_duration,
        "total_duration_hours": total_duration / 3600,
        "average_song_duration": avg_song_duration,
        "oldest_year": oldest_year,
        "newest_year": newest_year,
        "collaboration_count": collab_count,
        "solo_song_count": total_songs - collab_count
    }

def get_recommended_similar_songs(song_id: int, limit: int = 5) -> List[Dict]:
    """Get songs similar to a given song based on album, artists, and tags."""
    song_id_str = str(song_id)
    if song_id_str not in DB["songs"]:
        return []
    
    reference_song = DB["songs"][song_id_str]
    similar_songs = []
    
    for sid, song in DB["songs"].items():
        if sid == song_id_str:
            continue
        
        similarity_score = 0
        
        # Same album
        if song["album_id"] == reference_song["album_id"]:
            similarity_score += 3
        
        # Shared artists
        shared_artists = set(song["artist_ids"]) & set(reference_song["artist_ids"])
        similarity_score += len(shared_artists) * 2
        
        # Shared tags
        shared_tags = set(song["tag_ids"]) & set(reference_song["tag_ids"])
        similarity_score += len(shared_tags)
        
        if similarity_score > 0:
            similar_songs.append((similarity_score, song))
    
    similar_songs.sort(key=lambda x: x[0], reverse=True)
    return [song for score, song in similar_songs[:limit]]


# ==================== GEMINI FUNCTION DECLARATIONS ====================

tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="search_songs",
                description="Search for songs with multiple filters including duration range",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for song title"},
                        "artist_name": {"type": "string", "description": "Filter by artist name"},
                        "album_name": {"type": "string", "description": "Filter by album name"},
                        "tag_name": {"type": "string", "description": "Filter by tag name"},
                        "min_duration": {"type": "integer", "description": "Minimum duration in seconds"},
                        "max_duration": {"type": "integer", "description": "Maximum duration in seconds"},
                        "limit": {"type": "integer", "description": "Max results", "default": 10}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="get_song_details",
                description="Get complete details about a specific song",
                parameters={
                    "type": "object",
                    "properties": {
                        "song_id": {"type": "integer", "description": "Song ID"}
                    },
                    "required": ["song_id"]
                }
            ),
            types.FunctionDeclaration(
                name="get_artist_info",
                description="Get artist information and their songs",
                parameters={
                    "type": "object",
                    "properties": {
                        "artist_id": {"type": "integer", "description": "Artist ID"},
                        "artist_name": {"type": "string", "description": "Artist name"}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="get_album_info",
                description="Get album information and its songs",
                parameters={
                    "type": "object",
                    "properties": {
                        "album_id": {"type": "integer", "description": "Album ID"},
                        "album_name": {"type": "string", "description": "Album name"}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="get_random_songs",
                description="Get random songs with optional tag filter",
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "description": "Number of songs", "default": 5},
                        "tag_name": {"type": "string", "description": "Optional tag filter"}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="list_all_artists",
                description="List all artists in database",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max results", "default": 50}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="list_all_albums",
                description="List all albums with optional year filter",
                parameters={
                    "type": "object",
                    "properties": {
                        "year": {"type": "integer", "description": "Filter by year"},
                        "limit": {"type": "integer", "description": "Max results", "default": 50}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="list_all_tags",
                description="List all available tags/categories",
                parameters={"type": "object", "properties": {}}
            ),
            types.FunctionDeclaration(
                name="get_songs_by_year",
                description="Get songs from a specific year",
                parameters={
                    "type": "object",
                    "properties": {
                        "year": {"type": "integer", "description": "Year"},
                        "limit": {"type": "integer", "description": "Max results", "default": 20}
                    },
                    "required": ["year"]
                }
            ),
            types.FunctionDeclaration(
                name="get_artist_collaborations",
                description="Get collaboration songs for an artist",
                parameters={
                    "type": "object",
                    "properties": {
                        "artist_id": {"type": "integer", "description": "Artist ID"}
                    },
                    "required": ["artist_id"]
                }
            ),
            types.FunctionDeclaration(
                name="get_top_artists_by_song_count",
                description="Get artists with most songs",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max results", "default": 10}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="get_albums_by_decade",
                description="Get albums from a specific decade",
                parameters={
                    "type": "object",
                    "properties": {
                        "decade": {"type": "integer", "description": "Starting year of decade (e.g., 2010)"},
                        "limit": {"type": "integer", "description": "Max results", "default": 50}
                    },
                    "required": ["decade"]
                }
            ),
            types.FunctionDeclaration(
                name="get_longest_songs",
                description="Get longest songs with optional tag filter",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max results", "default": 10},
                        "tag_name": {"type": "string", "description": "Optional tag filter"}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="get_shortest_songs",
                description="Get shortest songs with optional tag filter",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max results", "default": 10},
                        "tag_name": {"type": "string", "description": "Optional tag filter"}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="get_artist_statistics",
                description="Get comprehensive statistics about an artist",
                parameters={
                    "type": "object",
                    "properties": {
                        "artist_id": {"type": "integer", "description": "Artist ID"}
                    },
                    "required": ["artist_id"]
                }
            ),
            types.FunctionDeclaration(
                name="get_album_statistics",
                description="Get comprehensive statistics about an album",
                parameters={
                    "type": "object",
                    "properties": {
                        "album_id": {"type": "integer", "description": "Album ID"}
                    },
                    "required": ["album_id"]
                }
            ),
            types.FunctionDeclaration(
                name="search_by_duration_range",
                description="Search songs by duration in minutes",
                parameters={
                    "type": "object",
                    "properties": {
                        "min_minutes": {"type": "integer", "description": "Min duration in minutes", "default": 0},
                        "max_minutes": {"type": "integer", "description": "Max duration in minutes", "default": 10},
                        "limit": {"type": "integer", "description": "Max results", "default": 20}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="get_artist_collaborators",
                description="Get all artists who collaborated with a specific artist",
                parameters={
                    "type": "object",
                    "properties": {
                        "artist_id": {"type": "integer", "description": "Artist ID"}
                    },
                    "required": ["artist_id"]
                }
            ),
            types.FunctionDeclaration(
                name="get_songs_by_year_range",
                description="Get songs from a range of years",
                parameters={
                    "type": "object",
                    "properties": {
                        "start_year": {"type": "integer", "description": "Start year"},
                        "end_year": {"type": "integer", "description": "End year"},
                        "limit": {"type": "integer", "description": "Max results", "default": 50}
                    },
                    "required": ["start_year", "end_year"]
                }
            ),
            types.FunctionDeclaration(
                name="get_multi_artist_songs",
                description="Get songs with multiple artists",
                parameters={
                    "type": "object",
                    "properties": {
                        "min_artists": {"type": "integer", "description": "Minimum number of artists", "default": 2},
                        "limit": {"type": "integer", "description": "Max results", "default": 20}
                    }
                }
            ),
            types.FunctionDeclaration(
                name="search_songs_fuzzy",
                description="Fuzzy search allowing partial word matches",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "threshold": {"type": "integer", "description": "Match threshold", "default": 3},
                        "limit": {"type": "integer", "description": "Max results", "default": 10}
                    },
                    "required": ["query"]
                }
            ),
            types.FunctionDeclaration(
                name="get_database_statistics",
                description="Get comprehensive statistics about the entire database",
                parameters={"type": "object", "properties": {}}
            ),
            types.FunctionDeclaration(
                name="get_recommended_similar_songs",
                description="Get songs similar to a given song based on artists, album, and tags",
                parameters={
                    "type": "object",
                    "properties": {
                        "song_id": {"type": "integer", "description": "Reference song ID"},
                        "limit": {"type": "integer", "description": "Max results", "default": 5}
                    },
                    "required": ["song_id"]
                }
            )
        ]
    )
]


# ==================== FUNCTION DISPATCHER ====================

FUNCTION_MAP = {
    "search_songs": search_songs,
    "get_song_details": get_song_details,
    "get_artist_info": get_artist_info,
    "get_album_info": get_album_info,
    "get_random_songs": get_random_songs,
    "list_all_artists": list_all_artists,
    "list_all_albums": list_all_albums,
    "list_all_tags": list_all_tags,
    "get_songs_by_year": get_songs_by_year,
    "get_artist_collaborations": get_artist_collaborations,
    "get_top_artists_by_song_count": get_top_artists_by_song_count,
    "get_albums_by_decade": get_albums_by_decade,
    "get_longest_songs": get_longest_songs,
    "get_shortest_songs": get_shortest_songs,
    "get_artist_statistics": get_artist_statistics,
    "get_album_statistics": get_album_statistics,
    "search_by_duration_range": search_by_duration_range,
    "get_artist_collaborators": get_artist_collaborators,
    "get_songs_by_year_range": get_songs_by_year_range,
    "get_multi_artist_songs": get_multi_artist_songs,
    "search_songs_fuzzy": search_songs_fuzzy,
    "get_database_statistics": get_database_statistics,
    "get_recommended_similar_songs": get_recommended_similar_songs
}