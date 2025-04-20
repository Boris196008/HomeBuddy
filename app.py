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

# Analyze image route (Pro only)
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
        return jsonify({"error": str(e)}), 500

# Run app
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
