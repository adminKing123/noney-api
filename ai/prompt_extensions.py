"""
Output-mode prompt extensions.

Each constant is appended to the model's base system prompt at request time
when the corresponding output option is enabled by the user.

Edit ONLY these strings to change the AI's output behaviour for each mode —
no other file needs to be touched.
"""

# ---------------------------------------------------------------------------
# HTML Preview mode
# Appended when the user enables "HTML Preview" in the UI.
# The frontend renders any ```htmlview code block in an iframe-style viewer.
# ---------------------------------------------------------------------------
HTML_PREVIEW_EXTENSION = """
OUTPUT MODE: HTML PREVIEW
You must produce a single, self-contained HTML file as your primary output.
Rules:
- Wrap the entire HTML output in a markdown code block using the language tag `htmlview`:
  ```htmlview
  <!DOCTYPE html>
  ...
  </html>
  ```
- All CSS must be inlined inside a <style> tag within <head>.
- All JavaScript must be inlined inside a <script> tag (no external CDN links unless strictly necessary and you explicitly note it).
- Do NOT split the output across multiple code blocks; everything goes in one `htmlview` block.
- You may still add a brief plain-text explanation before or after the code block.
"""

# ---------------------------------------------------------------------------
# Chart View mode
# Appended when the user enables "Chart View" in the UI.
# The frontend parses the <chartdata> tag and renders it with Chart.js via
# react-chartjs-2. The JSON must be compatible with Chart.js data objects.
# ---------------------------------------------------------------------------
CHART_VIEW_EXTENSION = """
OUTPUT MODE: CHART VIEW
You must produce chart data as your primary output using the custom <chartdata> tag.
Rules:
- Wrap the chart JSON inside a <chartdata> tag (no attributes needed):
  <chartdata>
  {
    "meta_data": {
      "title": "Descriptive chart title",
      "type": "bar"
    },
    "data": {
      // "data" object must be a valid Chart.js data object compatible with react-chartjs-2
    }
  }
  </chartdata>
- Supported chart types (meta_data.type): bar, line, pie, doughnut, radar, polarArea, bubble, scatter.
- The "data" object must be a valid Chart.js data object compatible with react-chartjs-2.
- You may include multiple <chartdata> blocks if more than one chart is appropriate.
- You may add plain-text analysis before or after each chart block.
- Do NOT wrap the JSON in a markdown code fence inside <chartdata>; raw JSON only.
"""
