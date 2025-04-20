from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
from openai import OpenAI
import sys
from flask_limiter import Limiter
import json
import base64

sys.stdout.reconfigure(line_buffering=True)
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app, origins=["https://lazy-gpt.webflow.io"])

def get_session_id():
    try:
        return request.cookies.get("session_id") or "no-session"
    except:
        return "no-session"

limiter = Limiter(key_func=get_session_id, app=app)

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

@app.after_request
def log_request(response):
    print(f"📡 IP: {request.remote_addr}, UA: {request.user_agent}, Session: {get_session_id()}, Status: {response.status_code}", flush=True)
    return response

@app.route('/')
def index():
    return "HomeBuddy API is running. Use POST /ask."

@app.route('/ask', methods=['POST'])
@limiter.limit("3 per minute")
def ask():
    try:
        data = request.get_json()
        data["from"] = "webflow"
        return handle_request(data)
    except:
        return jsonify({"error": "Invalid JSON"}), 400

def handle_request(data):
    user_input = data.get("message") or ""
    language = data.get("lang", "en")
    allowed = data.get("allowed", [])  # получено с фронта, e.g. ["\"Recipes\"", "\"Cleaning\""]

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    system_prompt = (
        "You are HomeBuddy — a friendly, minimal AI assistant for home tasks. "
        "Answer simply, clearly and in helpful tone. Avoid questions. No explanations. "
        "Just deliver a final result that’s practical and easy to understand for a homemaker."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        answer = response.choices[0].message.content

        if allowed:
            allowed_str = ", ".join(allowed)
            followup_prompt = (
                f"You are HomeBuddy assistant. Based on the answer below, suggest 3 follow-up actions "
                f"only from the following list: {allowed_str}. Respond in {language.upper()}.\n"
                "If none apply, return an empty list. Format: [{\"label\": \"...\", \"action\": \"...\"}]\n"
                "No links. No explanation. JSON only."
            )
        else:
            followup_prompt = (
                f"Based on the answer below, suggest 3 helpful follow-up actions. "
                f"Language: {language.upper()}.\n"
                "Format: [{\"label\": \"...\", \"action\": \"...\"}]\n"
                "No links. No repetition."
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

@app.route('/analyze-image', methods=['POST'])
@limiter.limit("3 per minute")
def analyze_image():
    session_id = get_session_id()
    if not session_id.startswith("pro_"):
        return jsonify({"error": "Access restricted to paid users only."}), 403

    image_file = request.files.get("image")
    if not image_file:
        return jsonify({"error": "Image file is missing."}), 400

    image_bytes = image_file.read()
    image_b64 = base64.b64encode(image_bytes).decode()

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You're a home assistant. Help suggest what to cook based on the contents of a fridge in the photo."},
                {"role": "user", "content": [
                    {"type": "text", "text": "What can I cook using what's visible in the photo?"},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}"
                    }}
                ]}
            ],
            max_tokens=300
        )
        result = response.choices[0].message.content
        return jsonify({"recipe": result})
    except Exception as e:
        return jsonify({"error": f"Error code: 400 - {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
