import analyzer.convolens as analyzer
from flask import Flask, request, jsonify
import json
import os

app = Flask(__name__)
analyzer = analyzer.ConversationAnalyzer()


@app.route("/api/analyze", methods=["POST"])
def analyze_conversation():
    try:
        if "conversation" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["conversation"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        # Read and parse JSON
        content = file.read().decode("utf-8")
        conversation_data = json.loads(content)

        # Validate data structure
        if not isinstance(conversation_data, list):
            return (
                jsonify({"error": "Invalid JSON format. Expected array of messages"}),
                400,
            )

        for msg in conversation_data:
            if (
                not isinstance(msg, dict)
                or "speaker" not in msg
                or "message" not in msg
            ):
                return (
                    jsonify(
                        {
                            "error": 'Invalid message format. Each message must have "speaker" and "message" fields'
                        }
                    ),
                    400,
                )

        # Analyze conversation
        results = analyzer.analyze_conversation(conversation_data)

        return jsonify(results)

    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON file"}), 400
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "true").lower() == "true",
        port=os.environ.get("FLASK_PORT", 5000),
    )
