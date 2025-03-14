// app.js
const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const { pipeline } = require('@xenova/transformers');
const hnswlib = require('hnswlib-node');

const app = express();
app.use(cors());
app.use(bodyParser.json());
app.use(express.static('template'));

// Sample data
const recommendations = [
    "Optimize irrigation scheduling",
    "Implement field health monitoring",
    "Set up pest & disease alerts",
    "Conduct soil analysis & fertilization advice",
    "Follow weather-based farming recommendations"
];

const detailed_knowledge = [
    // ... (your detailed knowledge entries)
];

// Initialize model and index
let embedder;
let index;
const initApp = async () => {
    try {
        // Load sentence embedding model
        embedder = await pipeline('feature-extraction', 'Xenova/all-mpnet-base-v2');
        
        // Create and populate HNSW index
        const numDimensions = 768;
        index = new hnswlib.HierarchicalNSW('cosine', numDimensions);
        index.initIndex(1000);
        
        // Add document embeddings
        const docVectors = await Promise.all(
            detailed_knowledge.map(async (doc) => {
                const output = await embedder(doc.title + ' ' + doc.description);
                return Array.from(output.data);
            })
        );
        
        docVectors.forEach((vector, idx) => {
            index.addPoint(vector, idx);
        });
        
        console.log('Index created with', index.getCurrentCount(), 'points');
    } catch (error) {
        console.error('Initialization error:', error);
        process.exit(1);
    }
};

// Routes
app.get('/', (req, res) => {
    res.sendFile(__dirname + '/template/index.html');
});

app.get('/recommendations', (req, res) => {
    res.json({
        count: recommendations.length,
        recommendations
    });
});

app.post('/details', async (req, res) => {
    try {
        const indexNum = parseInt(req.body.index);
        if (isNaN(indexNum) return res.status(400).json({ error: 'Invalid index format' });
        if (indexNum < 0 || indexNum >= recommendations.length) {
            return res.status(400).json({ error: 'Index out of range' });
        }

        const query = recommendations[indexNum];
        const queryVector = Array.from((await embedder(query)).data);
        
        const [nearestId] = index.searchKnn(queryVector, 1);
        
        res.json({
            recommendation: query,
            details: detailed_knowledge[nearestId]
        });
    } catch (error) {
        console.error('Details error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Start server
const PORT = process.env.PORT || 3000;
initApp().then(() => {
    app.listen(PORT, () => {
        console.log(`Server running on port ${PORT}`);
    });
});