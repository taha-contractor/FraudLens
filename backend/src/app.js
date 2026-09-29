import express from "express";
import helmet from "helmet";
import cors from "cors";
import healthRoutes from "./routes/health.routes.js";
import authRoutes from "./routes/auth.routes.js";
import { notFoundHandler, errorHandler } from "./middleware/error.middleware.js";

const app = express();

// Security-oriented defaults
app.disable("x-powered-by");
app.use(helmet());
app.use(cors());

// Request parsing
app.use(express.json({ limit: "100kb" }));
app.use(express.urlencoded({ extended: true, limit: "100kb" }));

// API routes (versioned)
app.use("/api/v1/health", healthRoutes);
app.use("/api/v1/auth", authRoutes);

// Unknown routes + centralized error handling (must stay last)
app.use(notFoundHandler);
app.use(errorHandler);

export default app;
