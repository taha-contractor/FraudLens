import express from "express";

const app = express();

app.use(express.json());
app.get("/", (req, res) => {
    res.json({
        message: "FraudLens API is running successfully.",
    });
});
export default app;