require('dotenv').config();
const express = require('express');
const path = require('path');
const cors = require('cors');
const { ChatClient } = require('@azure/communication-chat');
const { AzureCommunicationTokenCredential } = require('@azure/communication-common');

const app = express();
const port = 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const ACS_CONNECTION_STRING = process.env.ACS_CONNECTION_STRING;
const ACS_CHAT_THREAD_ID = process.env.ACS_CHAT_THREAD_ID;

let chatClient;

async function initializeChatClient() {
    try {
        chatClient = new ChatClient(ACS_CONNECTION_STRING, new AzureCommunicationTokenCredential(process.env.ACS_USER_ID));
        console.log("Azure Chat Client initialized.");
    } catch (error) {
        console.error("Error initializing Azure Chat Client:", error);
    }
}
initializeChatClient();

async function sendChatMessage(message) {
    if (!chatClient || !ACS_CHAT_THREAD_ID) {
        console.warn("Chat client not initialized or chat thread ID missing.");
        return;
    }
    try {
        const sendMessageRequest = { content: message };
        const sendMessageOptions = { senderDisplayName: "Expert System" };
        await chatClient.getChatThreadClient(ACS_CHAT_THREAD_ID).sendMessage(sendMessageRequest, sendMessageOptions);
        console.log("Message sent:", message);
    } catch (error) {
        console.error("Error sending chat message:", error);
    }
}

const expertRecommendations = [
    "Optimize irrigation scheduling",
    "Implement field health monitoring",
    "Set up pest & disease alerts",
    "Conduct soil analysis & fertilization advice",
    "Follow weather-based farming recommendations"
];

const detailedKnowledge = [
    "Use soil moisture sensors, adjust schedules, and implement drip irrigation.",
    "Monitor fields with drones, analyze soil nutrients, and use NDVI scans.",
    "Use pheromone traps, weather-based outbreak predictions, and image recognition.",
    "Perform seasonal soil analysis, optimize pH balance, and create custom fertilizer blends.",
    "Use microclimate models, early warning systems, and select crop varieties accordingly."
];

app.post('/send-recommendation', async (req, res) => {
    const { index } = req.body;
    if (index >= 0 && index < expertRecommendations.length) {
        const messageToSend = `**Recommendation:** ${expertRecommendations[index]}\n\n**Details:** ${detailedKnowledge[index]}`;
        await sendChatMessage(messageToSend);
        res.json({ message: "Recommendation sent to chat." });
    } else {
        res.status(400).json({ error: "Invalid index." });
    }
});

app.listen(port, () => console.log(`Server running on port ${port}`));