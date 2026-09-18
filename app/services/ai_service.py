import os
import json
import time
import logging
from google import genai

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {'Technical', 'Billing', 'Account', 'General'}
VALID_PRIORITIES = {'Low', 'Medium', 'High'}

# Primary model with backup options in case of 503 capacity spikes
MODELS_TO_TRY = ['gemini-3.6-flash', 'gemini-3.6-pro', 'gemini-2.0-flash']

def classify_ticket(subject: str, description: str) -> dict:
    fallback = {
        "category": "General",
        "priority": "Medium",
        "ai_summary": "Auto-classification unavailable."
    }

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY missing. Falling back to defaults.")
        return fallback

    prompt = f"""
Analyze this support ticket and return strict JSON with no markdown formatting:
Subject: {subject}
Description: {description}

Required schema:
{{
  "category": "Technical" | "Billing" | "Account" | "General",
  "priority": "Low" | "Medium" | "High",
  "ai_summary": "<One-sentence summary under 120 characters>"
}}
"""
    client = genai.Client(api_key=api_key)

    for model_name in MODELS_TO_TRY:
        for attempt in range(2):  # 2 attempts per model
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                
                raw_text = response.text.strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.strip("`").replace("json", "", 1).strip()
                    
                data = json.loads(raw_text)

                category = data.get("category") if data.get("category") in VALID_CATEGORIES else "General"
                priority = data.get("priority") if data.get("priority") in VALID_PRIORITIES else "Medium"
                summary = data.get("ai_summary", "").strip()[:500] or "No summary generated."

                return {
                    "category": category,
                    "priority": priority,
                    "ai_summary": summary
                }

            except Exception as exc:
                err_msg = str(exc)
                logger.warning(f"Attempt {attempt + 1} with {model_name} failed: {err_msg}")
                # If 503 (rate limit/spikes), sleep 1.5s before retrying or switching models
                if "503" in err_msg or "UNAVAILABLE" in err_msg:
                    time.sleep(1.5)
                else:
                    # Non-transient error (e.g. 404), move to next model immediately
                    break

    logger.error("All AI classification models and retries exhausted. Applying default fallback.")
    return fallback