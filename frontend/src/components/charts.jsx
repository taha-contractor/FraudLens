import {
    ResponsiveContainer,
    AreaChart,
    Area,
    BarChart,
    Bar,
    PieChart,
    Pie,
    Cell,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
} from "recharts";

const AXIS = { stroke: "#7d8ca8", fontSize: 12 };
const GRID = "#1c2a45";

const tooltipStyle = {
    contentStyle: {
        background: "#0e1729",
        border: "1px solid #1c2a45",
        borderRadius: 8,
        fontSize: 12,
        color: "#e6ebf5",
    },
    labelStyle: { color: "#b3c0d6" },
};

export function ActivityAreaChart({ data, dataKey = "transactionCount", xKey = "label", height = 260 }) {
    return (
        <ResponsiveContainer width="100%" height={height}>
            <AreaChart data={data} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                <defs>
                    <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                    </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={16} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={48} />
                <Tooltip {...tooltipStyle} />
                <Area type="monotone" dataKey={dataKey} stroke="#38bdf8" strokeWidth={2} fill="url(#areaFill)" name="Transactions" />
            </AreaChart>
        </ResponsiveContainer>
    );
}

export function AmountBarChart({ data, xKey = "label", yKey = "value", height = 260, color = "#38bdf8" }) {
    return (
        <ResponsiveContainer width="100%" height={height}>
            <BarChart data={data} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={16} />
                <YAxis tick={AXIS} tickLine={false} axisLine={false} width={56} />
                <Tooltip {...tooltipStyle} cursor={{ fill: "#121d33" }} />
                <Bar dataKey={yKey} fill={color} radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
        </ResponsiveContainer>
    );
}

export function RiskPieChart({ data, height = 240 }) {
    const COLORS = { HIGH: "#f87171", MEDIUM: "#fbbf24", LOW: "#34d399", "Not assessed": "#2b3d5f" };
    return (
        <ResponsiveContainer width="100%" height={height}>
            <PieChart>
                <Pie
                    data={data}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={54}
                    outerRadius={82}
                    paddingAngle={2}
                    stroke="none"
                >
                    {data.map((entry) => (
                        <Cell key={entry.name} fill={COLORS[entry.name] || "#2b3d5f"} />
                    ))}
                </Pie>
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
        </ResponsiveContainer>
    );
}
