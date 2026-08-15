import express from "express";
import transactionRoutes from "./routes/transaction.routes.js";
const app = express();

app.use(express.json());
app.get("/", (req, res) => {
    res.json({
        message: "FraudLens API is running successfully.",
    });
});
app.use("/api/transactions", transactionRoutes);
export default app;