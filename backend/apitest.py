allow_origins=[
    "http://127.0.0.1:3000",
    "http://localhost:3000"
],

from flask import Flask, request, jsonify
from backend.analyze_answer import evaluate_answer

app = Flask(__name__)

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()
        question = data.get("question")
        answer = data.get("answer")

        result = evaluate_answer(question, answer)
        return jsonify(result)

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500
from flask_cors import CORS
CORS(app)


if __name__ == "__main__":
    app.run(debug=True)
