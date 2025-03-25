const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 5000;
const DOMAIN = 'localhost'; // Change to 'localhost' for local testing

app.use(cors());
app.use(bodyParser.json());

// FAO URLs for best practices
const FAO_URLS = [
    "https://www.fao.org/climate-smart-agriculture/en/",
    "https://www.fao.org/sustainable-agriculture/en/",
    "https://www.fao.org/soils-portal/soil-management/en/",
    "https://www.fao.org/water/en/",
    "https://www.fao.org/digital-agriculture/en/"
];

// Expert recommendations with corresponding best practices
const recommendations = [
    {
        title: "Optimize irrigation scheduling",
        detail: "Use soil moisture sensors and weather forecasts to adjust watering schedules efficiently.",
        source: FAO_URLS[3]
    },
    {
        title: "Implement field health monitoring",
        detail: "Deploy drones or satellite imagery to assess crop health and detect stress early.",
        source: FAO_URLS[4]
    },
    // ... (other recommendations)
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

// Serve static files from the public directory
app.use(express.static('public'));

// Get all recommendations
app.get('/api/recommendations', (req, res) => {
    res.json({ recommendations });
});

// Get detailed information about a specific recommendation
app.post('/api/details', (req, res) => {
    const { index } = req.body;

    if (typeof index !== 'number' || index < 0 || index >= recommendations.length) {
        return res.status(400).json({ error: 'Invalid index. Please provide a valid recommendation index.' });
    }

    res.json(recommendations[index]);
});

// Get label counts
app.get('/api/labels_counts', (req, res) => {
    const labelsCountsPath = path.join(__dirname, 'Labels_counts.json');
    fs.readFile(labelsCountsPath, 'utf8', (err, data) => {
        if (err) {
            return res.status(500).json({ error: 'Failed to read labels counts file' });
        }
        res.json(JSON.parse(data));
    });
});

// Serve the dashboard.html file
app.get('/dashboard', (req, res) => {
    res.sendFile(path.join(__dirname, 'dashboard.html'));
});

// Start the server on the specified domain and port
app.listen(PORT, DOMAIN, () => {
    console.log(`Server running on http://${DOMAIN}:${PORT}`);
});
