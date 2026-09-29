import mongoose from "mongoose";

/**
 * Centralized MongoDB access layer (Mongoose).
 * All database connection concerns live here so the rest of the
 * application never has to depend on driver details directly.
 */

let eventLoggingAttached = false;

function attachConnectionLogging() {
    if (eventLoggingAttached) return;
    eventLoggingAttached = true;

    mongoose.connection.on("connected", () => {
        console.log("[db] MongoDB connection established");
    });
    mongoose.connection.on("disconnected", () => {
        console.warn("[db] MongoDB connection lost");
    });
    mongoose.connection.on("reconnected", () => {
        console.log("[db] MongoDB reconnected");
    });
    mongoose.connection.on("error", (error) => {
        console.error("[db] MongoDB error:", error.message);
    });
}

/**
 * Connects to MongoDB using the MONGODB_URI environment variable.
 * @throws {Error} when MONGODB_URI is not configured
 */
export const connectDatabase = async () => {
    const uri = process.env.MONGODB_URI;
    if (!uri) {
        throw new Error("MONGODB_URI is not set. Configure it in backend/.env (see .env.example).");
    }

    attachConnectionLogging();

    await mongoose.connect(uri, {
        serverSelectionTimeoutMS: 5000,
    });
};

/**
 * Gracefully closes the MongoDB connection.
 */
export const disconnectDatabase = async () => {
    await mongoose.disconnect();
};

/**
 * Returns a safe, high-level label of the current connection state.
 * Never exposes hosts, credentials or driver internals.
 * @returns {"connected" | "connecting" | "disconnecting" | "disconnected"}
 */
export const getDatabaseStatus = () => {
    switch (mongoose.connection.readyState) {
        case 1:
            return "connected";
        case 2:
            return "connecting";
        case 3:
            return "disconnecting";
        default:
            return "disconnected";
    }
};

export default mongoose;
