from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
from openai import OpenAI
import sys
from flask_limiter import Limiter
import json
import base64

# Enable live logs
sys.stdout.reconfigure(line_buffering=True)

# Load environment variables
load_dotenv()

# OpenAI client setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Flask app setup
app = Flask(__name__)
CORS(app, origins=["https://lazy-gpt.webflow.io"])

# Get session ID from cookies
def get_session_id():
    try:
        return request.cookies.get("session_id") or "no-session"
    except:
        return "no-session"

# Request limiter per session
limiter = Limiter(key_func=get_session_id, app=app)

# Block bots without proper js_token
@app.before_request
def reject_invalid_token():
    if request.path == "/ask" and request.method == "POST":
        try:
            data = request.get_json()
            if data.get("js_token") != "genuine-human":
                print("🚩 Bot without js_token — rejected", flush=True)
                return jsonify({"error": "Bot detected — invalid token"}), 403
        except:
            return jsonify({"error": "Malformed request"}), 403

# Request logging
@app.after_request
def log_request(response):
    print(f"📡 IP: {request.remote_addr}, UA: {request.user_agent}, Session: {get_session_id()}, Status: {response.status_code}", flush=True)
    return response

# Root route
@app.route('/')
def index():
    return "HomeBuddy API is running. Use POST /ask."

# Main chat route
@app.route('/ask', methods=['POST'])
@limiter.limit("3 per minute")
def ask():
    try:
        data = request.get_json()
        data["from"] = "webflow"
        return handle_request(data)
    except:
        return jsonify({"error": "Invalid JSON"}), 400

# Chat handler logic
def handle_request(data):
    user_input = data.get("message") or ""
    is_webflow = data.get("from") == "webflow"
    language = data.get("lang", "en")
    allowed = data.get("allowed", [])

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    system_prompt = (
        "You are HomeBuddy — a friendly, minimal AI assistant for home tasks. "
        "Answer simply, clearly and in helpful tone. Avoid questions. No explanations. "
        "Just deliver a final result that’s practical and easy to understand for a homemaker."
    )

    try:
        # основной ответ
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        answer = response.choices[0].message.content

        # follow-up prompt
        if allowed:
            allowed_str = ", ".join(allowed)
            followup_prompt = (
                f"You are HomeBuddy assistant. Based on the answer below, suggest 3 relevant follow-up actions.\n"
                f"Only use actions from this list: {allowed_str}. Respond in {language.upper()}.\n"
                "If nothing fits — return an empty list.\n\n"
                "Format: [{\"label\": \"...\", \"action\": \"...\"}]\n"
                "Avoid links. Keep it short and practical."
            )
        else:
            followup_prompt = (
                f"Based on the following answer, suggest 3 smart follow-up actions in JSON format.\n"
                f"Language: {language.upper()}.\n"
                "Format: [{\"label\": \"...\", \"action\": \"...\"}]\nNo links, no repetition."
            )

        followup_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": followup_prompt},
                {"role": "user", "content": answer}
            ]
        )

        raw = followup_response.choices[0].message.content.strip()
        try:
            if "```" in raw:
                raw = raw.split("```")[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
            suggestions = json.loads(raw)
        except:
            suggestions = []

        return jsonify({"response": answer, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Run app
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
