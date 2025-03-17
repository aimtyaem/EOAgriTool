const express = require("express");

const app = express();
const PORT = 8000;

// Set up EJS for rendering templates
app.set("view engine", "ejs");

// Agriculture Knowledge Base
const AGRICULTURE_KNOWLEDGE_BASE = {
    recommendations: [
        "Implement precision irrigation scheduling",
        "Adopt integrated pest management",
        "Use soil moisture sensors",
        "Apply crop rotation strategies",
        "Monitor weather patterns for planting",
        "Utilize organic fertilizers",
        "Practice conservation tillage",
        "Install windbreaks for soil protection"
    ],
    details: [
        `Precision Irrigation Best Practices:
        - Use soil moisture sensors for data-driven watering
        - Implement drip irrigation systems
        - Schedule irrigation during cooler hours
        - Monitor evapotranspiration rates
        - Adjust for crop growth stages`,

        `Integrated Pest Management:
        - Regular field scouting
        - Use biological control agents
        - Implement trap cropping
        - Apply targeted pesticides
        - Maintain pest monitoring records`
    ]
};

// Function to generate recommendation cards
function generateRecommendationCards(numCards = 3) {
    const recommendations = AGRICULTURE_KNOWLEDGE_BASE.recommendations;
    const details = AGRICULTURE_KNOWLEDGE_BASE.details;

    // Select random recommendations
    const shuffled = recommendations.sort(() => 0.5 - Math.random());
    const selectedRecommendations = shuffled.slice(0, Math.min(numCards, recommendations.length));

    // Create recommendation cards
    const recommendationCards = selectedRecommendations.map(rec => {
        const detailIndex = recommendations.indexOf(rec);
        return {
            title: rec,
            details: details[detailIndex] || "Additional information not available."
        };
    });

    return recommendationCards;
}

// Home Route
app.get("/", (req, res) => {
    res.render("index", { recommendations: generateRecommendationCards() });
});

// API Route
app.get("/api/recommendations", (req, res) => {
    res.json(generateRecommendationCards());
});

// Start the server
app.listen(PORT, () => {
    console.log(`Server is running on http://0.0.0.0:${PORT}`);
});