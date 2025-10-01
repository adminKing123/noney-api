from events import send_event, send_step, send_start_step, send_end_step, send_text, send_searching_event
from flask import Flask, request, Response, jsonify, stream_with_context
from config import CONFIG
# from google import genai
from google.genai import client as CliAI
from google.genai import types
from flask_cors import CORS
import os
import json
from arsongs_functions import (
    tools,
    FUNCTION_MAP
)

client = CliAI.Client(api_key=CONFIG["GEMINI_API_KEY"])

config = types.GenerateContentConfig(
    tools=tools,
)

app = Flask(__name__)
CORS(app)

# In-memory storage for chat histories (use Redis/DB for production)
chat_histories = {}


def get_or_create_chat(chat_uid):
    """
    Get existing chat or create new one based on chat_uid.
    
    Args:
        chat_uid: Unique identifier for the chat session
        
    Returns:
        chat object from Gemini API
    """
    if chat_uid not in chat_histories:
        # Create new chat session
        chat = client.chats.create(
            model="gemini-2.0-flash-exp",
            config=config
        )
        chat_histories[chat_uid] = {
            'chat': chat,
            'history': []
        }
    
    return chat_histories[chat_uid]['chat']


def process_response_recursive(chat, prompt, chat_uid, max_iterations=5):
    """
    Recursively process model responses and handle function calls.
    
    Args:
        chat: Gemini chat object
        prompt: User's message
        chat_uid: Unique chat identifier
        max_iterations: Maximum number of recursive calls to prevent infinite loops
        
    Yields:
        Text chunks and events for streaming
    """
    if max_iterations <= 0:
        yield send_text("\n\n[Max function call iterations reached]")
        return
    
    # Send message to chat
    response = chat.send_message_stream(prompt)

    function_calls_made = []
    has_text = False
    collected_text = []

    # Process response chunks
    for chunk in response:
        if hasattr(chunk, 'candidates') and chunk.candidates:
            for candidate in chunk.candidates:
                for part in candidate.content.parts:
                    # Handle text responses
                    if hasattr(part, 'text') and part.text:
                        has_text = True
                        collected_text.append(part.text)
                        yield send_text(part.text)

                    # Handle function calls
                    if hasattr(part, 'function_call') and part.function_call:
                        func_name = part.function_call.name
                        func_args = dict(part.function_call.args)
                        
                        yield send_searching_event(title=f"Calling: {func_name}")
                        
                        # Execute the function
                        try:
                            result = FUNCTION_MAP[func_name](**func_args)
                            print(f"Function: {func_name}, Args: {func_args}, Result: {result}")
                            
                            function_calls_made.append({
                                "name": func_name,
                                "args": func_args,
                                "result": result
                            })
                            
                        except Exception as func_error:
                            print(f"Function execution error: {func_error}")
                            error_result = {"error": str(func_error)}
                            function_calls_made.append({
                                "name": func_name,
                                "args": func_args,
                                "result": error_result
                            })

    # Update chat history storage
    if chat_uid in chat_histories:
        chat_histories[chat_uid]['history'].append({
            'user': prompt,
            'model': ''.join(collected_text) if collected_text else None,
            'function_calls': function_calls_made if function_calls_made else None
        })

    # If function calls were made, send function responses back
    if function_calls_made:
        # Add spacing if there was text before function calls
        if has_text:
            yield send_text("\n\n")
        
        # Create function response parts
        function_response_parts = []
        for fc in function_calls_made:
            function_response_parts.append(
                types.Part.from_function_response(
                    name=fc["name"],
                    response={"result": fc["result"]}
                )
            )
        
        # Send function responses and get next model response
        next_response = chat.send_message_stream(function_response_parts)
        
        # Process the model's response to function calls
        for chunk in next_response:
            if hasattr(chunk, 'candidates') and chunk.candidates:
                for candidate in chunk.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            yield send_text(part.text)


@app.route("/generate", methods=["POST"])
def chat_endpoint():
    data = request.get_json()
    prompt = data.get("prompt")
    chat_uid = data.get("chat_uid")
    
    if not chat_uid:
        return jsonify({"error": "chat_uid is required"}), 400

    def generate():
        try:
            yield send_start_step()
            
            # Get or create chat session
            chat = get_or_create_chat(chat_uid)
            
            # Process the message with function calling support
            yield from process_response_recursive(chat, prompt, chat_uid)
            
            yield send_end_step()
            
        except Exception as e:
            print(f"Error in generate: {e}")
            yield send_text(f"\n\nError: {str(e)}")
            yield send_end_step()
    
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, host="0.0.0.0", port=port)