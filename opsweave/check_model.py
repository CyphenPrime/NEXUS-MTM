import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from core.llm import call_model


def main():
    print("Checking model access...")
    print(f"Provider: {config.PROVIDER}")
    print(f"Model:    {config.MODEL}")

    if not config.API_KEY or config.API_KEY == "your_key_here":
        print("\n[WARNING] LLM_API_KEY is not configured in .env. Please set a valid API key first.")
        return 1

    system_prompt = "You are a setup verification assistant. You must respond with valid JSON only."
    user_prompt = 'Return JSON {"ok": true}'

    result = call_model(area="reading", system=system_prompt, user=user_prompt)

    print("\n--- Model Call Result ---")
    print(f"Status:   {result['status']}")
    print(f"Model:    {result['model']}")
    print(f"Seconds:  {result['seconds']}")
    print(
        f"Tokens:   input={result['input_tokens']}, output={result['output_tokens']}, "
        f"thinking={result['thinking_tokens']}, total={result['total_tokens']}"
    )

    if result["status"] == "error":
        print(f"Error:    {result['error']}")
        return 1

    print(f"Raw Output: {result['output']}")

    parsed_json = False
    try:
        data = json.loads(result["output"].strip())
        parsed_json = isinstance(data, dict) and data.get("ok") is True
    except Exception as e:
        parsed_json = False
        print(f"JSON Parse Error: {e}")

    print(f"Parsed JSON successfully: {parsed_json}")
    return 0 if parsed_json else 1


if __name__ == "__main__":
    sys.exit(main())
