import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

app = Flask(__name__, template_folder=os.path.abspath('templates'))
CORS(app)

# Initialize model and data
model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

recommendations = [
    "Optimize irrigation scheduling",
    "Implement field health monitoring",
    "Set up pest & disease alerts",
    "Conduct soil analysis & fertilization advice",
    "Follow weather-based farming recommendations"
]

detailed_knowledge = [
    # ... (keep your detailed knowledge entries)
    # Example entry format:
    {
        "title": "Irrigation Optimization",
        "description": "Use soil moisture sensors to determine optimal watering times...",
        "steps": ["Install sensors", "Analyze data", "Implement schedule"]
    }
]

# Create FAISS index
doc_embeddings = np.array([model.encode(doc["title"] + " " + doc["description"]) for doc in detailed_knowledge])
index = faiss.IndexFlatL2(doc_embeddings.shape[1])
index.add(doc_embeddings)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/recommendations', methods=['GET'])
def get_recommendations():
    return jsonify({
        "count": len(recommendations),
        "recommendations": recommendations
    })

@app.route('/details', methods=['POST'])
def get_details():
    data = request.json
    if not data or 'index' not in data:
        return jsonify({"error": "Missing index parameter"}), 400
    
    try:
        index_num = int(data['index'])
    except ValueError:
        return jsonify({"error": "Invalid index format"}), 400

    if not 0 <= index_num < len(recommendations):
        return jsonify({"error": "Index out of range"}), 400

    query = recommendations[index_num]
    query_embedding = model.encode(query)
    _, indices = index.search(np.array([query_embedding]), k=1)
    
    return jsonify({
        "recommendation": recommendations[index_num],
        "details": detailed_knowledge[indices[0][0]]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))