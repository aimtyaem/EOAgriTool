from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

app = Flask(__name__)

# Initialize the sentence transformer model
model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

# Expert recommendations
recommendations = [
    "Optimize irrigation scheduling",
    "Implement field health monitoring",
    "Set up pest & disease alerts",
    "Conduct soil analysis & fertilization advice",
    "Follow weather-based farming recommendations"
]

# Detailed knowledge base for each recommendation
detailed_knowledge = [
    """Irrigation Scheduling Details:
- Use soil moisture sensors for precision watering
- Adjust schedules based on crop growth stages
- Consider evapotranspiration rates
- Implement drip irrigation for efficiency""",

    """Field Health Monitoring Details:
- Regular satellite imagery analysis
- Drone-based NDVI scans weekly
- Soil nutrient level tracking
- Early stress detection algorithms""",

    """Pest & Disease Alerts Details:
- Automated pheromone trap monitoring
- Weather-based outbreak prediction
- Image recognition for disease identification
- Integrated pest management strategies""",

    """Soil Analysis Details:
- Seasonal nutrient profiling
- pH balance optimization
- Organic matter content analysis
- Custom fertilizer blending recommendations""",

    """Weather-based Farming Details:
- Microclimate prediction models
- Frost/heatwave early warning systems
- Rainfall pattern adaptation
- Crop variety selection advisor"""
]

# Create embeddings for detailed knowledge
doc_embeddings = np.array([model.encode(doc) for doc in detailed_knowledge])

# Build FAISS index
index = faiss.IndexFlatL2(doc_embeddings.shape[1])
index.add(doc_embeddings)

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    return jsonify(recommendations)

@app.route('/details', methods=['POST'])
def get_details():
    data = request.json
    recommendation_index = data.get('index')
    
    if recommendation_index is None or not 0 <= recommendation_index < len(recommendations):
        return jsonify({"error": "Invalid recommendation index"}), 400
    
    # Get relevant details using semantic search
    query = recommendations[recommendation_index]
    query_embedding = model.encode(query)
    _, indices = index.search(np.array([query_embedding]), k=1)
    
    return jsonify({
        "recommendation": recommendations[recommendation_index],
        "details": detailed_knowledge[indices[0][0]]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
