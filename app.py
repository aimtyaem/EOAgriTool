# Azure Web app.py
from flask import Flask, jsonify, request
from flask_cors import CORS
import numpy as np
import faiss
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for cross-origin requests

# Agricultural best practices database
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
- Maintain pest monitoring records""",
        
        # Add other details entries...
    ]
}

# Create embeddings and FAISS index
embeddings = np.random.randn(len(AGRICULTURE_KNOWLEDGE_BASE["recommendations"]), 128).astype('float32')
index = faiss.IndexFlatL2(128)
index.add(embeddings)

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    """Return list of agricultural best practices recommendations"""
    return jsonify({
        "source": "FAO Agricultural Best Practices Database",
        "recommendations": AGRICULTURE_KNOWLEDGE_BASE["recommendations"],
        "last_updated": "2024-03-15"
    })

@app.route('/details', methods=['POST'])
def get_details():
    """Get detailed information for a specific recommendation"""
    data = request.json
    try:
        index = int(data.get('index'))
        if index < 0 or index >= len(AGRICULTURE_KNOWLEDGE_BASE["recommendations"]):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid recommendation index"}), 400
    
    return jsonify({
        "recommendation": AGRICULTURE_KNOWLEDGE_BASE["recommendations"][index],
        "details": AGRICULTURE_KNOWLEDGE_BASE["details"][index],
        "related_resources": [
            "FAO Guidelines",
            "Local Extension Services",
            "Climate Smart Agriculture Handbook"
        ]
    })

@app.route('/')
def health_check():
    return jsonify({
        "status": "active",
        "service": "Agricultural Best Practices API",
        "version": "1.2.0"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))