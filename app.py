from flask import Flask, render_template, jsonify
import random

app = Flask(__name__)

# Agriculture Knowledge Base
AGRICULTURE_KNOWLEDGE_BASE = {
    "recommendations": [
        "Implement precision irrigation scheduling",
        "Adopt integrated pest management",
        "Use soil moisture sensors",
        "Apply crop rotation strategies",
        "Monitor weather patterns for planting",
        "Utilize organic fertilizers",
        "Practice conservation tillage",
        "Install windbreaks for soil protection"
    ],
    "details": [
        """Precision Irrigation Best Practices:
        - Use soil moisture sensors for data-driven watering
        - Implement drip irrigation systems
        - Schedule irrigation during cooler hours
        - Monitor evapotranspiration rates
        - Adjust for crop growth stages""",

        """Integrated Pest Management:
        - Regular field scouting
        - Use biological control agents
        - Implement trap cropping
        - Apply targeted pesticides
        - Maintain pest monitoring records"""
    ]
}

def generate_recommendation_cards(num_cards=3):
    """
    Generates recommendation dashboard cards for farmers.
    """
    recommendations = AGRICULTURE_KNOWLEDGE_BASE["recommendations"]
    details = AGRICULTURE_KNOWLEDGE_BASE["details"]

    selected_recommendations = random.sample(recommendations, min(num_cards, len(recommendations)))

    recommendation_cards = []
    for rec in selected_recommendations:
        detail_index = recommendations.index(rec) if recommendations.index(rec) < len(details) else None
        recommendation_cards.append({
            "title": rec,
            "details": details[detail_index] if detail_index is not None else "Additional information not available."
        })

    return recommendation_cards

@app.route("/")
def home():
    return render_template("index.html", recommendations=generate_recommendation_cards())

@app.route("/api/recommendations")
def api_recommendations():
    return jsonify(generate_recommendation_cards())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)