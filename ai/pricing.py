"""
Gemini model pricing calculator.

Prices sourced from: https://ai.google.dev/gemini-api/docs/pricing (June 2026)
All prices are in USD on the paid tier, per 1,000,000 tokens unless noted.

Supported model identifiers correspond exactly to the `model_id` values in
AI_MAPPINGS (config.py):
  - gemini-2.5-flash
  - gemini-2.5-pro
  - gemini-3-flash-preview
  - imagen-4.0-generate-001
"""

# ---------------------------------------------------------------------------
# Pricing table — (USD / 1M tokens, paid tier)
# ---------------------------------------------------------------------------
_PRICING: dict = {
    # ---- Gemini 2.5 Flash ------------------------------------------------
    # Input:  $0.30 / 1M tokens (text / image / video)
    # Output: $2.50 / 1M tokens (includes thinking tokens)
    "gemini-2.5-flash": {
        "input_per_mtok": 0.30,
        "output_per_mtok": 2.50,
    },

    # ---- Gemini 2.5 Pro --------------------------------------------------
    # Input:  $1.25 / 1M (≤ 200k prompt tokens), $2.50 / 1M (> 200k)
    # Output: $10.00 / 1M (≤ 200k),               $15.00 / 1M (> 200k)
    "gemini-2.5-pro": {
        "input_per_mtok": 1.25,
        "output_per_mtok": 10.00,
        "input_per_mtok_large": 2.50,
        "output_per_mtok_large": 15.00,
        "large_threshold": 200_000,       # token count that triggers large-context rate
    },

    # ---- Gemini 3 Flash Preview ------------------------------------------
    # Input:  $0.50 / 1M tokens (text / image / video)
    # Output: $3.00 / 1M tokens (includes thinking tokens)
    "gemini-3-flash-preview": {
        "input_per_mtok": 0.50,
        "output_per_mtok": 3.00,
    },

    # ---- Imagen 4.0 Standard (fixed cost per image, no token pricing) ---
    # Output: $0.04 per image
    "imagen-4.0-generate-001": {
        "per_image_usd": 0.04,
    },
}

# Fallback per-image cost when the model is not found in the table
_DEFAULT_PER_IMAGE_USD: float = 0.039


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_text(gemini_model_id: str, input_tokens: int, output_tokens: int) -> dict:
    """
    Calculate the USD cost for a text / code / HRMS generation call.

    Args:
        gemini_model_id: Actual Gemini model identifier (e.g. 'gemini-2.5-flash').
        input_tokens:    Input tokens consumed.
        output_tokens:   Output tokens generated (thinking tokens included).

    Returns:
        dict:
            input_tokens  – int
            output_tokens – int
            total_tokens  – int
            cost_usd      – float (rounded to 8 decimal places)
            model_id      – str
    """
    pricing = _PRICING.get(gemini_model_id, {})
    threshold = pricing.get("large_threshold", float("inf"))

    # Use large-context rates if the prompt exceeds the threshold
    if input_tokens > threshold:
        input_rate = pricing.get("input_per_mtok_large", pricing.get("input_per_mtok", 0.0))
        output_rate = pricing.get("output_per_mtok_large", pricing.get("output_per_mtok", 0.0))
    else:
        input_rate = pricing.get("input_per_mtok", 0.0)
        output_rate = pricing.get("output_per_mtok", 0.0)

    cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": round(cost, 8),
        "model_id": gemini_model_id,
    }


def calculate_image(gemini_model_id: str, num_images: int = 1, input_tokens: int = 0) -> dict:
    """
    Calculate the USD cost for an image generation call.

    Text input tokens (aspect-ratio detection step, etc.) are priced at the
    model's text-input rate. Each generated image is priced at a fixed per-image fee.

    Args:
        gemini_model_id: Actual Gemini image model identifier.
        num_images:      Number of images generated in this request.
        input_tokens:    Text input tokens used during the request.

    Returns:
        dict:
            input_tokens     – int
            output_tokens    – 0 (images are not token-priced here)
            total_tokens     – int (equals input_tokens)
            images_generated – int
            cost_usd         – float (rounded to 8 decimal places)
            model_id         – str
    """
    pricing = _PRICING.get(gemini_model_id, {})
    input_rate = pricing.get("input_per_mtok", 0.0)
    per_image = pricing.get("per_image_usd", _DEFAULT_PER_IMAGE_USD)

    input_cost = (input_tokens * input_rate) / 1_000_000
    image_cost = num_images * per_image
    total_cost = input_cost + image_cost

    return {
        "input_tokens": input_tokens,
        "output_tokens": 0,
        "total_tokens": input_tokens,
        "images_generated": num_images,
        "cost_usd": round(total_cost, 8),
        "model_id": gemini_model_id,
    }
