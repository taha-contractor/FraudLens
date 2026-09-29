import { getDatabaseStatus } from "../config/database.js";

/**
 * GET /api/v1/health
 * Reports API liveness and MongoDB connectivity without exposing
 * credentials, hosts or driver internals.
 */
export const getHealth = (req, res) => {
    const database = getDatabaseStatus();

    res.status(200).json({
        success: true,
        service: "FraudLens API",
        status: database === "connected" ? "healthy" : "degraded",
        database,
        timestamp: new Date().toISOString(),
    });
};
