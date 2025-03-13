from flask import Flask, request, jsonify, render_template
from flask_cors import CORS  # Required for cross-origin requests
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

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
    
    # ... (keep other detailed knowledge entries the same)
]

# Create embeddings and FAISS index
doc_embeddings = np.array([model.encode(doc) for doc in detailed_knowledge])
index = faiss.IndexFlatL2(doc_embeddings.shape[1])
index.add(doc_embeddings)

# Serve HTML interface
@app.route('/')
def home():
    return render_template('index.html')  # Make sure index.html is in templates/ folder

# Existing API endpoints
@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    return jsonify(recommendations)

@app.route('/details', methods=['POST'])
def get_details():
    data = request.json
    recommendation_index = data.get('index')
    
    if recommendation_index is None or not 0 <= recommendation_index < len(recommendations):
        return jsonify({"error": "Invalid recommendation index"}), 400

    query = recommendations[recommendation_index]
    query_embedding = model.encode(query)
    _, indices = index.search(np.array([query_embedding]), k=1)
    
    return jsonify({
        "recommendation": recommendations[recommendation_index],
        "details": detailed_knowledge[indices[0][0]]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)