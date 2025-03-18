from flask import Flask, render_template, jsonify
import random
import requests

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
    """
    Generates AI-driven recommendations based on sensor data.
    """
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

def fetch_real_time_best_practices():
    """
    Fetches web-based best practices for farm management.
    """
    try:
        response = requests.get("https://api.farmmanagement.best-practices.com/agriculture")
        if response.status_code == 200:
            return response.json().get("best_practices", [])
        else:
            return [{"title": "Web Data Unavailable", "details": "Real-time recommendations could not be retrieved."}]
    except Exception as e:
        return [{"title": "Error Fetching Data", "details": str(e)}]

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

@app.route("/")
def home():
    sensor_data = get_sensor_data()
    recommendations = generate_expert_recommendations(sensor_data)
    web_best_practices = fetch_real_time_best_practices()
    
    return render_template("index.html", sensor_data=sensor_data, recommendations=recommendations, web_best_practices=web_best_practices)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)