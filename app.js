const express = require('express');
const bodyParser = require('body-parser');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(bodyParser.json());

// Mock data for recommendations
const recommendations = [
    { title: "Use Organic Fertilizers", details: "Organic fertilizers improve soil health and crop yield." },
    { title: "Implement Crop Rotation", details: "Crop rotation helps in maintaining soil fertility." },
    { title: "Adopt Drip Irrigation", details: "Drip irrigation conserves water and increases efficiency." }
];

// Endpoint to get recommendations
app.get('/api/recommendations', (req, res) => {
    res.json(recommendations);
});

// Endpoint to get recommendation details
app.post('/api/details', (req, res) => {
    const { index } = req.body;
    if (index >= 0 && index < recommendations.length) {
        res.json(recommendations[index]);
    } else {
        res.status(404).json({ error: 'Recommendation not found' });
    }
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});