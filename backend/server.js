import "dotenv/config";
import app from "./src/app.js";
import { connectDatabase, disconnectDatabase } from "./src/config/database.js";

const PORT = Number(process.env.PORT) || 5000;

async function start() {
    // Attempt the MongoDB connection up front. If it fails, the HTTP API
    // still starts so that /api/v1/health can honestly report the database
    // status; Mongoose keeps retrying in the background.
    try {
        await connectDatabase();
        console.log("[startup] MongoDB connected");
    } catch (error) {
        console.error(
            `[startup] MongoDB connection failed: ${error.message} ` +
            "(the API will start anyway and report database status via /api/v1/health)"
        );
    }

    const server = app.listen(PORT, () => {
        console.log(`[startup] FraudLens API listening on http://localhost:${PORT}`);
    });

    const shutdown = async (signal) => {
        console.log(`[shutdown] Received ${signal}, closing server...`);
        server.close(async () => {
            await disconnectDatabase().catch(() => {});
            process.exit(0);
        });
    };

    process.on("SIGINT", () => shutdown("SIGINT"));
    process.on("SIGTERM", () => shutdown("SIGTERM"));
}

start();
