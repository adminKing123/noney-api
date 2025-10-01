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


@app.route("/generate", methods=["POST"])
def chat():
    data = request.get_json()
    prompt = data.get("prompt")

    def generate():
        try:
            yield send_start_step()
            response = client.models.generate_content_stream(
                model="gemini-2.0-flash-exp",
                config=config,
                contents=prompt,
            )

            for chunk in response:
                if hasattr(chunk, 'candidates') and chunk.candidates:
                    for candidate in chunk.candidates:
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                yield send_text(part.text)

                            if hasattr(part, 'function_call') and part.function_call:
                                func_name = part.function_call.name
                                func_args = dict(part.function_call.args)
                                yield send_searching_event(title=f"Function Calling: {func_name} ${func_args}")

                                result = FUNCTION_MAP[func_name](**func_args)

                                print(func_name, func_args)


            yield send_end_step()
        except Exception as e:
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