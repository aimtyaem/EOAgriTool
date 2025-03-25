const { EmailClient } = require("@azure/communication-email");

async function sendEmail() {
    const connectionString = "endpoint=https://eoagritool.africa.communication.azure.com/;accesskey=EKcca3DMi2dnF9WCgoAcdaFbg5x1zyXiJwnwQ3hRTSbwJI0njIVdJQQJ99BCACULyCphvvTgAAAAAZCSk3Vm";
    
    try {
        const emailClient = new EmailClient(connectionString);
        
        const emailMessage = {
            senderAddress: "verified-email@yourdomain.com", // MUST BE PRE-VERIFIED
            content: {
                subject: "Test Email from ACS",
                plainText: "This is a test email body",
            },
            recipients: {
                to: [{ address: "aimt16@hotmail.com" }],
            },
        };

        const poller = await emailClient.beginSend(emailMessage);
        const result = await poller.pollUntilDone();
        
        console.log("Email sent with ID:", result.id);
    } catch (error) {
        console.error("Failed to send email:");
        console.error("- Status code:", error.statusCode);
        console.error("- Error message:", error.message);
        if (error.details) console.error("- Details:", error.details);
    }
}

// Execute the function
sendEmail();