from flask import Flask, jsonify, request
from flask_cors import CORS
import numpy as np

app = Flask(__name__)
CORS(app)

# Expert recommendations
recommendations = [
    "Optimize irrigation scheduling",
    "Implement field health monitoring",
    "Set up pest & disease alerts",
    "Conduct soil analysis & fertilization advice",
    "Follow weather-based farming recommendations"
]

# Detailed knowledge base for each recommendation
detailed_knowledge = {
    "Optimize irrigation scheduling": """Irrigation Scheduling Details:
- Use soil moisture sensors for precision watering
- Adjust schedules based on crop growth stages
- Consider evapotranspiration rates
- Implement drip irrigation for efficiency""",

    "Implement field health monitoring": """Field Health Monitoring Details:
- Regular satellite imagery analysis
- Drone-based NDVI scans weekly
- Soil nutrient level tracking
- Early stress detection algorithms""",

    "Set up pest & disease alerts": """Pest & Disease Alerts Details:
- Automated pheromone trap monitoring
- Weather-based outbreak prediction
- Image recognition for disease identification
- Integrated pest management strategies""",

    "Conduct soil analysis & fertilization advice": """Soil Analysis Details:
- Seasonal nutrient profiling
- pH balance optimization
- Organic matter content analysis
- Custom fertilizer blending recommendations""",

    "Follow weather-based farming recommendations": """Weather-based Farming Details:
- Microclimate prediction models
- Frost/heatwave early warning systems
- Rainfall pattern adaptation
- Crop variety selection advisor"""
}

# Convert recommendations into numerical vectors for search
def text_to_vector(text):
    return np.array([ord(char) for char in text])

recommendation_vectors = {rec: text_to_vector(rec) for rec in recommendations}

def find_best_match(query):
    """Find the most relevant recommendation using cosine similarity"""
    query_vector = text_to_vector(query)
    similarities = {
        rec: np.dot(query_vector, rec_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(rec_vector))
        for rec, rec_vector in recommendation_vectors.items()
    }
    return max(similarities, key=similarities.get)

@app.route('/')
def home():
    return jsonify({"message": "Welcome to the Agricultural Expert System API!"})

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    return jsonify({"recommendations": recommendations})

@app.route('/recommendation/detail', methods=['GET'])
def get_recommendation_detail():
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    best_match = find_best_match(query)
    detail = detailed_knowledge.get(best_match, "No details available.")

    return jsonify({
        "query": query,
        "matched_recommendation": best_match,
        "details": detail
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)