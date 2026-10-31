"""Small wrapper for Gemini's current Interactions API."""

from google import genai


def generate_text(prompt: str, api_key: str, model_name: str, json_mode: bool = False) -> str:
    """Generate text with Gemini and return the model's text output."""
    if not api_key:
        raise ValueError("A Gemini API key is required for online generation.")

    client = genai.Client(api_key=api_key)
    request = {
        "model": model_name,
        "input": prompt,
    }
    if json_mode:
        request["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
        }

    interaction = client.interactions.create(**request)
    output = getattr(interaction, "output_text", None)
    if not output or not output.strip():
        raise RuntimeError("Gemini returned an empty response.")
    return output.strip()
