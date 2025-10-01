from events import send_event, send_step, send_start_step, send_end_step, send_text, send_searching_event
from flask import Flask, request, Response, jsonify, stream_with_context
from config import CONFIG
from google import genai
from google.genai import types
from flask_cors import CORS
import os
import json
from arsongs_functions import (
    tools, raw_tools,
    FUNCTION_MAP  # Import the function map for execution
)

client = genai.Client(api_key=CONFIG["GEMINI_API_KEY"])

config = types.GenerateContentConfig(
    tools=tools,
    # tools=raw_tools,
    # system_instruction=system_instruction
)

app = Flask(__name__)
CORS(app)


def process_response_recursive(conversation_history, max_iterations=5):
    """
    Recursively process model responses and handle function calls.
    
    Args:
        conversation_history: List of conversation turns
        max_iterations: Maximum number of recursive calls to prevent infinite loops
        
    Yields:
        Text chunks and events for streaming
    """
    if max_iterations <= 0:
        yield send_text("\n\n[Max function call iterations reached]")
        return
    
    # Make API call
    response = client.models.generate_content_stream(
        model="gemini-2.0-flash-exp",
        config=config,
        contents=conversation_history,
    )

    function_calls_made = []
    model_parts = []
    has_text = False

    # Process response chunks
    for chunk in response:
        if hasattr(chunk, 'candidates') and chunk.candidates:
            for candidate in chunk.candidates:
                for part in candidate.content.parts:
                    # Handle text responses
                    if hasattr(part, 'text') and part.text:
                        has_text = True
                        model_parts.append({"text": part.text})
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
                                "function_call": part.function_call,
                                "result": result
                            })
                            model_parts.append({"function_call": part.function_call})
                            
                        except Exception as func_error:
                            print(f"Function execution error: {func_error}")
                            error_result = {"error": str(func_error)}
                            function_calls_made.append({
                                "function_call": part.function_call,
                                "result": error_result
                            })
                            model_parts.append({"function_call": part.function_call})

    # If function calls were made, add them to history and recurse
    if function_calls_made:
        # Add model's response with function calls to history
        conversation_history.append({
            "role": "model",
            "parts": model_parts
        })
        
        # Add function responses to history
        for fc in function_calls_made:
            conversation_history.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": fc["function_call"].name,
                        "response": {"result": fc["result"]}
                    }
                }]
            })
        
        # Add spacing if there was text before function calls
        if has_text:
            yield send_text("\n\n")
        
        # Recursively process the next response
        yield from process_response_recursive(conversation_history, max_iterations - 1)


@app.route("/generate", methods=["POST"])
def chat():
    data = request.get_json()
    prompt = data.get("prompt")

    def generate():
        try:
            yield send_start_step()
            conversation_history = [{"role": "user", "parts": [{"text": prompt}]}]
            yield from process_response_recursive(conversation_history)
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