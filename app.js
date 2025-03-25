const express = require("express");

const app = express();
const PORT = 8000;

// Set up EJS for rendering templates
app.set("view engine", "ejs");

// FAO Best Practices URLs
const FAO_URLS = {
    climate_smart_agriculture: "https://www.fao.org/climate-smart-agriculture/en/",
    sustainable_agriculture: "https://www.fao.org/sustainable-agriculture/en/",
    soil_management: "https://www.fao.org/soils-portal/soil-management/en/",
    water_management: "https://www.fao.org/water/en/",
    digital_agriculture: "https://www.fao.org/digital-agriculture/en/"
};

// Agriculture Knowledge Base with Expert Recommendations
const AGRICULTURE_KNOWLEDGE_BASE = [
    {
        title: "Implement Precision Irrigation Scheduling",
        details: `Precision Irrigation Best Practices:
        - Use soil moisture sensors for data-driven watering
        - Implement drip irrigation systems
        - Schedule irrigation during cooler hours
        - Monitor evapotranspiration rates
        - Adjust for crop growth stages`,
        source: FAO_URLS.water_management
    },
    {
        title: "Adopt Integrated Pest Management",
        details: `Integrated Pest Management:
        - Regular field scouting
        - Use biological control agents
        - Implement trap cropping
        - Apply targeted pesticides
        - Maintain pest monitoring records`,
        source: FAO_URLS.climate_smart_agriculture
    },
    {
        title: "Use Soil Moisture Sensors",
        details: `Soil moisture sensors help monitor soil water levels to prevent over-irrigation and water waste.`,
        source: FAO_URLS.water_management
    },
    {
        title: "Apply Crop Rotation Strategies",
        details: `Crop rotation improves soil fertility and reduces pests by changing plant species each season.`,
        source: FAO_URLS.soil_management
    },
    {
        title: "Monitor Weather Patterns for Planting",
        details: `Using climate data helps optimize planting schedules and reduce risks from extreme weather.`,
        source: FAO_URLS.climate_smart_agriculture
    },
    {
        title: "Utilize Organic Fertilizers",
        details: `Organic fertilizers improve soil health while reducing environmental impact.`,
        source: FAO_URLS.soil_management
    },
    {
        title: "Practice Conservation Tillage",
        details: `Reducing tillage minimizes soil erosion and retains soil moisture for better crop growth.`,
        source: FAO_URLS.sustainable_agriculture
    },
    {
        title: "Install Windbreaks for Soil Protection",
        details: `Planting trees or shrubs as windbreaks prevents soil erosion and protects crops from wind damage.`,
        source: FAO_URLS.sustainable_agriculture
    },
    {
        title: "Leverage Digital Farming Tools",
        details: `Use satellite imagery, IoT sensors, and AI-based analytics to improve decision-making in agriculture.`,
        source: FAO_URLS.digital_agriculture
    }
];

// Function to generate a random selection of recommendations
function generateRecommendationCards(numCards = 3) {
    // Select random recommendations without modifying the original array
    const shuffled = [...AGRICULTURE_KNOWLEDGE_BASE].sort(() => 0.5 - Math.random());
    return shuffled.slice(0, Math.min(numCards, AGRICULTURE_KNOWLEDGE_BASE.length));
}

// Home Route (renders recommendations)
app.get("/", (req, res) => {
    res.render("index", { recommendations: generateRecommendationCards() });
});

// API Route (returns recommendations in JSON format)
app.get("/api/recommendations", (req, res) => {
    res.json(generateRecommendationCards());
});

// API Route to fetch a specific recommendation by index
app.get("/api/recommendations/:index", (req, res) => {
    const index = parseInt(req.params.index, 10);
    if (isNaN(index) || index < 0 || index >= AGRICULTURE_KNOWLEDGE_BASE.length) {
        return res.status(400).json({ error: "Invalid index. Please provide a valid recommendation index." });
    }
    res.json(AGRICULTURE_KNOWLEDGE_BASE[index]);
});

// Start the server
app.listen(PORT, () => {
    console.log(`Server is running on http://exprec-fse3f6ffh6fehmb6.canadacentral-01.azurewebsites.net:${PORT}`);
});