const express = require("express");

const app = express();
const PORT = 8000;

// Set up EJS for rendering templates
app.set("view engine", "ejs");

// FAO Best Practices URLs
const FAO_URLS = [
    "https://www.fao.org/climate-smart-agriculture/en/",
    "https://www.fao.org/sustainable-agriculture/en/",
    "https://www.fao.org/soils-portal/soil-management/en/",
    "https://www.fao.org/water/en/",
    "https://www.fao.org/digital-agriculture/en/"
];

// Agriculture Knowledge Base with Expert Recommendations
const AGRICULTURE_KNOWLEDGE_BASE = [
    {
        title: "Implement precision irrigation scheduling",
        details: `Precision Irrigation Best Practices:
        - Use soil moisture sensors for data-driven watering
        - Implement drip irrigation systems
        - Schedule irrigation during cooler hours
        - Monitor evapotranspiration rates
        - Adjust for crop growth stages`,
        source: FAO_URLS[3] // Water management
    },
    {
        title: "Adopt integrated pest management",
        details: `Integrated Pest Management:
        - Regular field scouting
        - Use biological control agents
        - Implement trap cropping
        - Apply targeted pesticides
        - Maintain pest monitoring records`,
        source: FAO_URLS[0] // Climate-smart agriculture
    },
    {
        title: "Use soil moisture sensors",
        details: `Soil moisture sensors help monitor soil water levels to prevent over-irrigation and water waste.`,
        source: FAO_URLS[3] // Water management
    },
    {
        title: "Apply crop rotation strategies",
        details: `Crop rotation improves soil fertility and reduces pests by changing plant species each season.`,
        source: FAO_URLS[2] // Soil management
    },
    {
        title: "Monitor weather patterns for planting",
        details: `Using climate data helps optimize planting schedules and reduce risks from extreme weather.`,
        source: FAO_URLS[0] // Climate-smart agriculture
    },
    {
        title: "Utilize organic fertilizers",
        details: `Organic fertilizers improve soil health while reducing environmental impact.`,
        source: FAO_URLS[2] // Soil management
    },
    {
        title: "Practice conservation tillage",
        details: `Reducing tillage minimizes soil erosion and retains soil moisture for better crop growth.`,
        source: FAO_URLS[1] // Sustainable agriculture
    },
    {
        title: "Install windbreaks for soil protection",
        details: `Planting trees or shrubs as windbreaks prevents soil erosion and protects crops from wind damage.`,
        source: FAO_URLS[1] // Sustainable agriculture
    }
];

// Function to generate random recommendation cards
function generateRecommendationCards(numCards = 3) {
    // Shuffle recommendations and pick a few
    const shuffled = AGRICULTURE_KNOWLEDGE_BASE.sort(() => 0.5 - Math.random());
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

// Start the server
app.listen(PORT, () => {
    console.log(`Server is running on http://20.48.204.5:${PORT}`);
});