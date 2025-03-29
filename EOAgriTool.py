from flask import Flask, render_template, jsonify, request
import random
import requests
from bs4 import BeautifulSoup
import concurrent.futures

app = Flask(__name__)

# Simulated IoT Sensor Data for Farming
def get_sensor_data():
    return {
        "soil_moisture": round(random.uniform(10, 60), 2),  # Percentage
        "temperature": round(random.uniform(15, 40), 2),  # Celsius
        "humidity": round(random.uniform(30, 90), 2)  # Percentage
    }

# AI-Driven Agriculture Knowledge Base
AGRICULTURE_KNOWLEDGE_BASE = {
    "low_moisture": "Increase irrigation frequency and consider soil amendments.",
    "high_moisture": "Reduce watering to prevent root rot and monitor drainage.",
    "high_temperature": "Implement shading techniques and adjust irrigation schedules.",
    "low_temperature": "Use row covers or greenhouses to maintain optimal warmth.",
    "high_humidity": "Increase ventilation and monitor for fungal diseases.",
    "low_humidity": "Use mulching techniques to retain soil moisture."
}

def generate_expert_recommendations(sensor_data):
    recommendations = []

    if sensor_data["soil_moisture"] < 20:
        recommendations.append({"title": "Soil Moisture Alert", "details": AGRICULTURE_KNOWLEDGE_BASE["low_moisture"]})
    elif sensor_data["soil_moisture"] > 50:
        recommendations.append({"title": "Soil Overwatering Risk", "details": AGRICULTURE_KNOWLEDGE_BASE["high_moisture"]})

    if sensor_data["temperature"] > 35:
        recommendations.append({"title": "Heat Stress Alert", "details": AGRICULTURE_KNOWLEDGE_BASE["high_temperature"]})
    elif sensor_data["temperature"] < 20:
        recommendations.append({"title": "Cold Stress Alert", "details": AGRICULTURE_KNOWLEDGE_BASE["low_temperature"]})

    if sensor_data["humidity"] > 80:
        recommendations.append({"title": "High Humidity Warning", "details": AGRICULTURE_KNOWLEDGE_BASE["high_humidity"]})
    elif sensor_data["humidity"] < 40:
        recommendations.append({"title": "Low Humidity Concern", "details": AGRICULTURE_KNOWLEDGE_BASE["low_humidity"]})

    return recommendations if recommendations else [{"title": "Optimal Conditions", "details": "No immediate actions required."}]

FAO_URLS = [
    "https://www.fao.org/climate-smart-agriculture/en/",
    "https://www.fao.org/sustainable-agriculture/en/",
    "https://www.fao.org/soils-portal/soil-management/en/",
    "https://www.fao.org/water/en/",
    "https://www.fao.org/digital-agriculture/en/"
]

def fetch_real_time_best_practices():
    best_practices = []
    headers = {"User-Agent": "Mozilla/5.0"}

    def fetch_data(url):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            titles = soup.find_all(["h2", "h3"], limit=5) or []
            paragraphs = soup.find_all("p", limit=5) or []

            return [
                {
                    "title": title.get_text(strip=True),
                    "details": paragraph.get_text(strip=True),
                    "source": url
                }
                for title, paragraph in zip(titles, paragraphs)
            ]
        except requests.exceptions.RequestException as e:
            return [{"title": "Error Fetching Data", "details": str(e), "source": url}]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(fetch_data, FAO_URLS)
    
    for result in results:
        best_practices.extend(result)

    return best_practices if best_practices else [{"title": "No Data", "details": "Could not retrieve best practices.", "source": "N/A"}]

@app.route("/api/dashboard")
def api_dashboard():
    sensor_data = get_sensor_data()
    recommendations = generate_expert_recommendations(sensor_data)
    web_best_practices = fetch_real_time_best_practices()
    return jsonify({
        "sensor_data": sensor_data,
        "recommendations": recommendations,
        "web_best_practices": web_best_practices
    })

@app.route("/api/sensor")
def api_sensor():
    return jsonify(get_sensor_data())

@app.route("/")
def home():
    sensor_data = get_sensor_data()
    recommendations = generate_expert_recommendations(sensor_data)
    web_best_practices = fetch_real_time_best_practices()
    return render_template("index.html", 
                         sensor_data=sensor_data,
                         recommendations=recommendations,
                         web_best_practices=web_best_practices)

@app.route("/api/delete_extension", methods=["DELETE"])
def delete_extension():
    extension_name = request.args.get("extension_name")
    if not extension_name:
        return jsonify({"error": "Extension name is required"}), 400

    # Replace with the actual URL and headers for your web app's API
    api_url = f"https://your-web-app-url/api/extensions/{extension_name}"
    headers = {"Authorization": "Bearer YOUR_API_TOKEN"}

    try:
        response = requests.delete(api_url, headers=headers)
        response.raise_for_status()
        return jsonify({"message": f"Extension '{extension_name}' deleted successfully"}), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
