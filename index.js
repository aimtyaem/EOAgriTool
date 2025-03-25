const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors'); // Added CORS support

const app = express();
const PORT = process.env.PORT || 5000;
const DOMAIN = 'https://exprec-fse3f6ffh6fehmb6.canadacentral-01.azurewebsites.net';

app.use(cors()); // Enable CORS for frontend communication
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
        source: FAO_URLS[3] // Water management
    },
    {
        title: "Implement field health monitoring",
        detail: "Deploy drones or satellite imagery to assess crop health and detect stress early.",
        source: FAO_URLS[4] // Digital agriculture
    },
    {
        title: "Set up pest & disease alerts",
        detail: "Install automated pest monitoring systems and receive AI-driven alerts for better disease management.",
        source: FAO_URLS[0] // Climate-smart agriculture
    },
    {
        title: "Conduct soil analysis & fertilization advice",
        detail: "Regularly test soil composition and apply fertilizers based on scientific soil analysis.",
        source: FAO_URLS[2] // Soil management
    },
    {
        title: "Follow weather-based farming recommendations",
        detail: "Leverage climate data to optimize planting and harvesting times, reducing weather-related risks.",
        source: FAO_URLS[0] // Climate-smart agriculture
    },
    {
        title: "Adopt climate-smart agricultural practices",
        detail: "Implement sustainable farming techniques such as crop rotation and integrated pest management.",
        source: FAO_URLS[1] // Sustainable agriculture
    },
    {
        title: "Improve soil organic matter with conservation agriculture",
        detail: "Apply no-till farming and cover crops to improve soil health and reduce erosion.",
        source: FAO_URLS[2] // Soil management
    },
    {
        title: "Integrate livestock and crop production",
        detail: "Utilize livestock manure for natural fertilization and maintain crop-livestock symbiosis.",
        source: FAO_URLS[1] // Sustainable agriculture
    },
    {
        title: "Use drought-resistant crop varieties",
        detail: "Plant drought-resistant and climate-adapted crop varieties to enhance resilience to extreme weather.",
        source: FAO_URLS[0] // Climate-smart agriculture
    },
    {
        title: "Enhance carbon sequestration through agroforestry",
        detail: "Adopt agroforestry techniques like intercropping trees with crops to boost biodiversity and carbon capture.",
        source: FAO_URLS[1] // Sustainable agriculture
    }
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

// Start the server on the specified domain and port
app.listen(PORT, DOMAIN, () => {
    console.log(`Server running on http://${DOMAIN}:${PORT}`);
});