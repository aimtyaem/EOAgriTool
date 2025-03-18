const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors'); // Added CORS support

const app = express();
const PORT = process.env.PORT || 5000;
const DOMAIN = '20.48.204.5';

app.use(cors()); // Enable CORS for frontend communication
app.use(bodyParser.json());

// Sample recommendations
const recommendations = [
    "Optimize irrigation scheduling",
    "Implement field health monitoring",
    "Set up pest & disease alerts",
    "Conduct soil analysis & fertilization advice",
    "Follow weather-based farming recommendations"
];

// Corresponding detailed knowledge for each recommendation
const detailed_knowledge = [
    "Use soil moisture sensors and weather forecasts to adjust watering schedules.",
    "Deploy drones or satellite imagery to assess crop health and detect stress early.",
    "Install automated pest monitoring systems and receive AI-driven alerts.",
    "Regularly test soil composition and apply fertilizers based on analysis.",
    "Leverage climate data to optimize planting and harvesting times."
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

// Get all recommendations
app.get('/api/recommendations', (req, res) => {
    res.json(recommendations);
});

// Get detailed information about a specific recommendation
app.post('/api/details', (req, res) => {
    const { index } = req.body;

    if (typeof index !== 'number' || index < 0 || index >= recommendations.length) {
        return res.status(400).json({ error: 'Invalid index. Please provide a valid recommendation index.' });
    }

    res.json({ detail: detailed_knowledge[index] });
});

// Start the server on the specified domain and port
app.listen(PORT, DOMAIN, () => {
    console.log(`Server running on http://${DOMAIN}:${PORT}`);
});