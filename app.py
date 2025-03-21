from flask import Flask, render_template, jsonify
import requests
import json

app = Flask(__name__)

# Fetch processed data from EO repository
def fetch_processed_data():
    response = requests.get('URL_TO_EO_REPO/output/processed_data.json')
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": "Failed to fetch data"}

@app.route("/content/output/processed_data.json")
def api_processed_data():
    data = fetch_processed_data()
    return jsonify(data)

@app.route("/")
def home():
    sensor_data = get_sensor_data()
    recommendations = generate_expert_recommendations(sensor_data)
    web_best_practices = fetch_real_time_best_practices()
    processed_data = fetch_processed_data()
    return render_template("dashboard.html",
                         sensor_data=sensor_data,
                         recommendations=recommendations,
                         web_best_practices=web_best_practices,
                         processed_data=processed_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)