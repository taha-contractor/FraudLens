import app from './src/app.js';
import connectDB from './src/config/database.js';
import 'dotenv/config';

const PORT = process.env.PORT || 5000;

await connectDB();

app.listen(PORT, () => {
    console.log(`FraudLens server running on http://localhost:${PORT}`);
});