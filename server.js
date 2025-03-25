const { EmailClient } = require("@azure/communication-email");

// Connection string from Azure portal
const connectionString = "endpoint=https://eoagritool.africa.communication.azure.com/;accesskey=EKcca3DMi2dnF9WCgoAcdaFbg5x1zyXiJwnwQ3hRTSbwJI0njIVdJQQJ99BCACULyCphvvTgAAAAAZCSk3Vm";

// Initialize the email client
const emailClient = new EmailClient(connectionString);

async function sendEmail() {
    try {
        // Create the email message
        const emailMessage = {
            senderAddress: "<Verified-Sender-Email>",  // Replace with your verified sender email
            content: {
                subject: "Welcome to Azure Communication Services Email",
                plainText: "This is plain text body",
                html: "<html><body>This is html body</body></html>",
            },
            recipients: {
                to: [
                    {
                        address: "<recipient-email>",  // Replace with recipient email
                        displayName: "Customer Name",
                    },
                ],
            },
        };

        // Send the email
        const poller = await emailClient.beginSend(emailMessage);
        const response = await poller.pollUntilDone();

        console.log("Email sent successfully. Operation ID:", response.id);
    } catch (error) {
        console.error("Error sending email:", error);
    }
}

sendEmail();