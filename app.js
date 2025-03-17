const express = require('express');
const bodyParser = require('body-parser');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(bodyParser.json());

// Sample data
const recommendations = [
    "Optimize irrigation scheduling",
    "Implement field health monitoring",
    "Set up pest & disease alerts",
    "Conduct soil analysis & fertilization advice",
    "Follow weather-based farming recommendations"
];

const detailed_knowledge = [
    // Add your knowledge base entries here
];

// Initialize application
const initApp = async () => {
    try {
        console.log("App initialized successfully.");
    } catch (error) {
        console.error("Failed to initialize app:", error);
    }
};

initApp();

// Endpoints
app.get('/api/recommendations', (req, res) => {
    res.json(recommendations);
});

app.post('/api/details', (req, res) => {
    const { index } = req.body;
    if (index >= 0 && index < recommendations.length) {
        res.json({ detail: detailed_knowledge[index] || "No additional details available." });
    } else {
        res.status(404).json({ error: 'Recommendation not found' });
    }
});

// Start the server
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});