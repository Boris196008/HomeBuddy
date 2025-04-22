from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import os
from dotenv import load_dotenv
from openai import OpenAI
import json


SESSION_USAGE = {}
FREE_LIMIT = 3

# === Setup ===
load_dotenv()
app = Flask(__name__)

def get_session_id():
    try:
        return request.cookies.get("session_id") or "no-session"
    except:
        return "no-session"


CORS(app,
     origins=["https://lazy-gpt.webflow.io"],
     supports_credentials=True,
     allow_headers=["Content-Type"])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/ask", methods=["POST", "OPTIONS"])
@cross_origin(
    origins=["https://lazy-gpt.webflow.io"],
    supports_credentials=True
)

def get_session_id():
    try:
        return request.cookies.get("session_id") or "no-session"
    except:
        return "no-session"

def is_pro_user(session_id):
    return session_id.startswith("pro_")

@app.route("/ask", methods=["POST", "OPTIONS"])
@cross_origin(origins=["https://lazy-gpt.webflow.io"], supports_credentials=True)
def ask():
    print("📥 Пришёл запрос на /ask", flush=True)
    session_id = get_session_id()
    is_pro = is_pro_user(session_id)

    try:
        data = request.get_json()
        print("🔍 session:", session_id, "| pro:", is_pro)

        # 👉 лимит
        if not is_pro:
            SESSION_USAGE[session_id] = SESSION_USAGE.get(session_id, 0) + 1
            if SESSION_USAGE[session_id] > FREE_LIMIT:
                return jsonify({
                    "error": "Free limit reached",
                    "pro": False
                }), 403

        # 💬 временный ответ
        return jsonify({
            "response": f"Принято. Это ваш {SESSION_USAGE.get(session_id, 1)} запрос.",
            "pro": is_pro
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


        if not user_input:
            return jsonify({"error": "No message provided"}), 400

        system_prompt = (
            "You are HomeBuddy — a friendly, minimal AI assistant for home tasks. "
            "Answer simply, clearly and in helpful tone. Avoid questions. No explanations. "
            "Just deliver a final result that’s practical and easy to understand for a homemaker."
        )

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )

        answer = response.choices[0].message.content
        return jsonify({ "response": answer })

    except Exception as e:
        return jsonify({ "error": str(e) }), 500

@app.route("/")
def index():
    return "HomeBuddy API is running (clean mode)."

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

