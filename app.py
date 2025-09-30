from flask import Flask, request, Response, jsonify, stream_with_context
from config import CONFIG
from google import genai
from google.genai import types
import json
import uuid
from flask_cors import CORS
import os

# Load dataset
with open("data.json", "r", encoding="utf-8") as f:
    SONGS = json.load(f)

# Create Gemini client
client = genai.Client(api_key=CONFIG["GEMINI_API_KEY"])

# Base URL for song files
BASE_SONG_URL = "https://raw.githubusercontent.com/harshcore/arsongs-src-copy/main/"

# Helper function to format song data
def format_song_info(song):
    """Format song data into a more readable structure with full URLs"""
    minutes = int(song["duration"] // 60)
    seconds = int(song["duration"] % 60)
    duration_formatted = f"{minutes}:{seconds:02d}"
    
    # Build full URLs
    song_url = BASE_SONG_URL + song["url"]
    thumbnail_300 = BASE_SONG_URL + song["album"]["thumbnail300x300"]
    thumbnail_1200 = BASE_SONG_URL + song["album"]["thumbnail1200x1200"]
    
    # Get artist thumbnails
    artist_thumbnails = []
    for artist in song["artists"]:
        artist_thumbnails.append({
            "name": artist["name"],
            "thumbnail_300": BASE_SONG_URL + artist["thumbnail300x300"],
            "thumbnail_1200": BASE_SONG_URL + artist["thumbnail1200x1200"]
        })
    
    return {
        "id": song["id"],
        "name": song["original_name"],
        "artists": [artist["name"] for artist in song["artists"]],
        "artist_details": artist_thumbnails,
        "album": song["album"]["title"],
        "year": song["album"]["year"],
        "duration": duration_formatted,
        "duration_seconds": song["duration"],
        "tags": [tag["name"] for tag in song["tags"]],
        "download_url": song_url,
        "thumbnail": thumbnail_300,
        "thumbnail_large": thumbnail_1200
    }

# Define function tools for song operations
def search_songs(query: str, limit: int = 10):
    """Search for songs by title, artist, or album name."""
    query_lower = query.lower()
    results = []
    
    for song in SONGS:
        # Search in title
        if query_lower in song["title"].lower() or query_lower in song["original_name"].lower():
            results.append(format_song_info(song))
            continue
        
        # Search in album
        if query_lower in song["album"]["title"].lower():
            results.append(format_song_info(song))
            continue
        
        # Search in artists
        for artist in song["artists"]:
            if query_lower in artist["name"].lower():
                results.append(format_song_info(song))
                break
        
        for tag in song["tags"]:
            if query_lower in tag["name"].lower():
                results.append(format_song_info(song))
                break
    
    return results[:limit]

def get_songs_by_artist(artist_name: str):
    """Get all songs by a specific artist."""
    artist_lower = artist_name.lower()
    results = []
    
    for song in SONGS:
        for artist in song["artists"]:
            if artist_lower in artist["name"].lower():
                results.append(format_song_info(song))
                break
    
    return results

def get_songs_by_album(album_name: str):
    """Get all songs from a specific album."""
    album_lower = album_name.lower()
    results = []
    
    for song in SONGS:
        if album_lower in song["album"]["title"].lower():
            results.append(format_song_info(song))
    
    return results

def get_songs_by_year(year: int):
    """Get all songs released in a specific year."""
    results = []
    
    for song in SONGS:
        if song["album"]["year"] == year:
            results.append(format_song_info(song))
    
    return results

def get_songs_by_tag(tag_name: str):
    """Get all songs with a specific tag (e.g., language)."""
    tag_lower = tag_name.lower()
    results = []
    
    for song in SONGS:
        for tag in song["tags"]:
            if tag_lower in tag["name"].lower():
                results.append(format_song_info(song))
                break
    
    return results

def get_random_songs(count: int = 5):
    """Get random songs from the library."""
    import random
    return [format_song_info(song) for song in random.sample(SONGS, min(count, len(SONGS)))]

def get_song_by_id(song_id: int):
    """Get a specific song by its ID."""
    for song in SONGS:
        if song["id"] == song_id:
            return format_song_info(song)
    return None

# Register tools with Gemini
tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="search_songs",
                description="Search for songs by title, artist name, or album name. Returns matching songs with full details.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (song title, artist name, or album name)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            ),
            types.FunctionDeclaration(
                name="get_songs_by_artist",
                description="Get all songs by a specific artist name.",
                parameters={
                    "type": "object",
                    "properties": {
                        "artist_name": {
                            "type": "string",
                            "description": "The name of the artist"
                        }
                    },
                    "required": ["artist_name"]
                }
            ),
            types.FunctionDeclaration(
                name="get_songs_by_album",
                description="Get all songs from a specific album.",
                parameters={
                    "type": "object",
                    "properties": {
                        "album_name": {
                            "type": "string",
                            "description": "The name of the album"
                        }
                    },
                    "required": ["album_name"]
                }
            ),
            types.FunctionDeclaration(
                name="get_songs_by_year",
                description="Get all songs released in a specific year.",
                parameters={
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "The release year"
                        }
                    },
                    "required": ["year"]
                }
            ),
            types.FunctionDeclaration(
                name="get_songs_by_tag",
                description="Get all songs with a specific tag (e.g., 'Hindi', 'English', etc.).",
                parameters={
                    "type": "object",
                    "properties": {
                        "tag_name": {
                            "type": "string",
                            "description": "The tag name (usually language)"
                        }
                    },
                    "required": ["tag_name"]
                }
            ),
            types.FunctionDeclaration(
                name="get_random_songs",
                description="Get random songs from the music library.",
                parameters={
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of random songs to return (default: 5)",
                            "default": 5
                        }
                    }
                }
            ),
            types.FunctionDeclaration(
                name="get_song_by_id",
                description="Get a specific song by its unique ID.",
                parameters={
                    "type": "object",
                    "properties": {
                        "song_id": {
                            "type": "integer",
                            "description": "The unique ID of the song"
                        }
                    },
                    "required": ["song_id"]
                }
            )
        ]
    )
]

# Function mapping
FUNCTION_MAP = {
    "search_songs": search_songs,
    "get_songs_by_artist": get_songs_by_artist,
    "get_songs_by_album": get_songs_by_album,
    "get_songs_by_year": get_songs_by_year,
    "get_songs_by_tag": get_songs_by_tag,
    "get_random_songs": get_random_songs,
    "get_song_by_id": get_song_by_id
}

# Enhanced system instruction for the AI
system_instruction = """"""

config = types.GenerateContentConfig(
    tools=tools,
    system_instruction=system_instruction
)

# Create Flask app
app = Flask(__name__)
CORS(app)

@app.route("/generate", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        prompt = data.get("prompt")
        
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400
        
        def generate():
            try:
                data = {
                    "id": str(uuid.uuid4()),
                    "data": [
                        {
                            "type": "connecting",
                            "title": "Please Wait",
                        }
                    ]
                }
                yield f"event: step\ndata: {json.dumps(data)}\n\n"
                
                response = client.models.generate_content_stream(
                    model="gemini-2.0-flash-exp",
                    config=config,
                    contents=prompt,
                )
                
                collected_sources = []
                
                for chunk in response:
                    if hasattr(chunk, 'candidates') and chunk.candidates:
                        for candidate in chunk.candidates:
                            # Collect all function calls in this chunk
                            function_calls = []
                            for part in candidate.content.parts:
                                if hasattr(part, 'function_call'):
                                    function_calls.append(part.function_call)
                            
                            # If we have function calls, execute them all
                            if function_calls:
                                function_response_parts = []
                                
                                for func_call in function_calls:
                                    func_name = func_call.name
                                    func_args = dict(func_call.args)

                                    data = {
                                        "id": str(uuid.uuid4()),
                                        "data": [
                                            {
                                                "type": "searching",
                                                "title": f"Searching: {func_name}",
                                            }
                                        ]
                                    }
                                    yield f"event: step\ndata: {json.dumps(data)}\n\n"
                                    
                                    # Execute the function
                                    if func_name in FUNCTION_MAP:
                                        result = FUNCTION_MAP[func_name](**func_args)
                                        
                                        # Collect the source data (original song objects for frontend)
                                        if isinstance(result, list):
                                            # Get original song objects for source data
                                            for formatted_song in result:
                                                original_song = next((s for s in SONGS if s["id"] == formatted_song["id"]), None)
                                                if original_song:
                                                    collected_sources.append(original_song)
                                        elif result and isinstance(result, dict):
                                            original_song = next((s for s in SONGS if s["id"] == result["id"]), None)
                                            if original_song:
                                                collected_sources.append(original_song)
                                        
                                        # Add function response part
                                        function_response_parts.append(
                                            types.Part(
                                                function_response=types.FunctionResponse(
                                                    name=func_name,
                                                    response={"result": result}
                                                )
                                            )
                                        )
                                
                                # Send all function responses back to the model at once
                                function_response_content = types.Content(
                                    parts=function_response_parts
                                )
                                
                                continue_response = client.models.generate_content_stream(
                                    model="gemini-2.0-flash-exp",
                                    config=config,
                                    contents=[prompt, candidate.content, function_response_content]
                                )
                                
                                for continue_chunk in continue_response:
                                    if continue_chunk.text:
                                        data = {
                                            "index": 0,
                                            "id": str(uuid.uuid4()),
                                            "data": continue_chunk.text,
                                        }
                                        yield f"event: text\ndata: {json.dumps(data)}\n\n"
                            else:
                                # No function calls, just stream the text
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        data = {
                                            "index": 0,
                                            "id": str(uuid.uuid4()),
                                            "data": part.text,
                                        }
                                        yield f"event: text\ndata: {json.dumps(data)}\n\n"
                
                # Send all collected source data at the end
                if collected_sources:
                    data = {
                        "id": str(uuid.uuid4()),
                        "data": collected_sources,
                    }
                    yield f"event: ar_songs_source_data\ndata: {json.dumps(data)}\n\n"

                data = {
                    "id": str(uuid.uuid4()),
                    "data": [
                        {
                            "type": "finished",
                            "title": f"Finished",
                        }
                    ]
                }
                yield f"event: step\ndata: {json.dumps(data)}\n\n"
                                
            except Exception as e:
                data = {
                    "id": str(uuid.uuid4()),
                    "data": [
                        {
                            "type": "error",
                            "title": f"Failed to generate response",
                            "description": str(e)
                        }
                    ]
                }
                yield f"event: step\ndata: {json.dumps(data)}\n\n"
                yield f"event: error\ndata: {str(e)}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4000))
    app.run(host="0.0.0.0", port=port)