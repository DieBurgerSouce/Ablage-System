/**
 * Chart Component Stories
 *
 * Chart-Komponenten für Visual Regression Testing.
 * Basiert auf Recharts.
 */

import type { Meta, StoryObj } from '@storybook/react';
import {
    LineChart,
    Line,
    BarChart,
    Bar,
    AreaChart,
    Area,
    PieChart,
    Pie,
    Cell,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { WaterfallChart, type WaterfallDataPoint } from '@/components/charts/WaterfallChart';

const meta: Meta = {
    title: 'UI/Charts',
    parameters: {
        layout: 'padded',
        docs: {
            description: {
                component: 'Chart-Komponenten basierend auf Recharts.',
            },
        },
    },
    tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof meta>;

// ==================== Sample Data ====================

const monthlyData = [
    { name: 'Jan', dokumente: 400, verarbeitet: 380 },
    { name: 'Feb', dokumente: 300, verarbeitet: 290 },
    { name: 'Mrz', dokumente: 500, verarbeitet: 480 },
    { name: 'Apr', dokumente: 450, verarbeitet: 440 },
    { name: 'Mai', dokumente: 600, verarbeitet: 570 },
    { name: 'Jun', dokumente: 550, verarbeitet: 530 },
    { name: 'Jul', dokumente: 700, verarbeitet: 680 },
    { name: 'Aug', dokumente: 650, verarbeitet: 620 },
    { name: 'Sep', dokumente: 800, verarbeitet: 770 },
    { name: 'Okt', dokumente: 750, verarbeitet: 720 },
    { name: 'Nov', dokumente: 900, verarbeitet: 860 },
    { name: 'Dez', dokumente: 850, verarbeitet: 810 },
];

const pieData = [
    { name: 'Rechnungen', value: 400, color: '#2563eb' },
    { name: 'Lieferscheine', value: 300, color: '#16a34a' },
    { name: 'Verträge', value: 200, color: '#dc2626' },
    { name: 'Angebote', value: 150, color: '#ca8a04' },
    { name: 'Sonstiges', value: 100, color: '#6b7280' },
];

const waterfallData: WaterfallDataPoint[] = [
    { name: 'Startwert', value: 10000, isSubtotal: true },
    { name: 'Rechnungen', value: 5000 },
    { name: 'Lieferungen', value: 3000 },
    { name: 'Gebühren', value: -1500 },
    { name: 'Rabatte', value: -800 },
    { name: 'Steuern', value: -2200 },
    { name: 'Endwert', value: 13500, isTotal: true },
];

// ==================== Line Chart ====================

export const LineChartDefault: Story = {
    render: () => (
        <Card className="w-[600px]">
            <CardHeader>
                <CardTitle>Dokumentenstatistik</CardTitle>
                <CardDescription>Monatliche Übersicht 2024</CardDescription>
            </CardHeader>
            <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={monthlyData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line
                            type="monotone"
                            dataKey="dokumente"
                            name="Hochgeladen"
                            stroke="#2563eb"
                            strokeWidth={2}
                        />
                        <Line
                            type="monotone"
                            dataKey="verarbeitet"
                            name="Verarbeitet"
                            stroke="#16a34a"
                            strokeWidth={2}
                        />
                    </LineChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    ),
};

// ==================== Area Chart ====================

export const AreaChartDefault: Story = {
    render: () => (
        <Card className="w-[600px]">
            <CardHeader>
                <CardTitle>Dokumentenvolumen</CardTitle>
                <CardDescription>Verlauf über das Jahr</CardDescription>
            </CardHeader>
            <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={monthlyData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Area
                            type="monotone"
                            dataKey="dokumente"
                            name="Dokumente"
                            stroke="#2563eb"
                            fill="#2563eb"
                            fillOpacity={0.3}
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    ),
};

export const AreaChartStacked: Story = {
    render: () => (
        <Card className="w-[600px]">
            <CardHeader>
                <CardTitle>Gestapelte Flaeche</CardTitle>
                <CardDescription>Vergleich Hochgeladen vs. Verarbeitet</CardDescription>
            </CardHeader>
            <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={monthlyData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Area
                            type="monotone"
                            dataKey="verarbeitet"
                            name="Verarbeitet"
                            stackId="1"
                            stroke="#16a34a"
                            fill="#16a34a"
                            fillOpacity={0.5}
                        />
                        <Area
                            type="monotone"
                            dataKey="dokumente"
                            name="Hochgeladen"
                            stackId="2"
                            stroke="#2563eb"
                            fill="#2563eb"
                            fillOpacity={0.3}
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    ),
};

// ==================== Bar Chart ====================

export const BarChartDefault: Story = {
    render: () => (
        <Card className="w-[600px]">
            <CardHeader>
                <CardTitle>Dokumentenvergleich</CardTitle>
                <CardDescription>Hochgeladen vs. Verarbeitet</CardDescription>
            </CardHeader>
            <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={monthlyData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar
                            dataKey="dokumente"
                            name="Hochgeladen"
                            fill="#2563eb"
                            radius={[4, 4, 0, 0]}
                        />
                        <Bar
                            dataKey="verarbeitet"
                            name="Verarbeitet"
                            fill="#16a34a"
                            radius={[4, 4, 0, 0]}
                        />
                    </BarChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    ),
};

export const BarChartHorizontal: Story = {
    render: () => {
        const data = [
            { name: 'Rechnungen', anzahl: 450 },
            { name: 'Lieferscheine', anzahl: 380 },
            { name: 'Verträge', anzahl: 220 },
            { name: 'Angebote', anzahl: 190 },
            { name: 'Mahnungen', anzahl: 85 },
        ];

        return (
            <Card className="w-[500px]">
                <CardHeader>
                    <CardTitle>Dokumenttypen</CardTitle>
                    <CardDescription>Nach Anzahl sortiert</CardDescription>
                </CardHeader>
                <CardContent>
                    <ResponsiveContainer width="100%" height={250}>
                        <BarChart layout="vertical" data={data}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis type="number" />
                            <YAxis dataKey="name" type="category" width={100} />
                            <Tooltip />
                            <Bar
                                dataKey="anzahl"
                                fill="#2563eb"
                                radius={[0, 4, 4, 0]}
                            />
                        </BarChart>
                    </ResponsiveContainer>
                </CardContent>
            </Card>
        );
    },
};

// ==================== Pie Chart ====================

export const PieChartDefault: Story = {
    render: () => (
        <Card className="w-[400px]">
            <CardHeader>
                <CardTitle>Dokumentverteilung</CardTitle>
                <CardDescription>Nach Dokumenttyp</CardDescription>
            </CardHeader>
            <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                        <Pie
                            data={pieData}
                            cx="50%"
                            cy="50%"
                            outerRadius={100}
                            dataKey="value"
                            label={({ name, percent }) =>
                                `${name} ${(percent * 100).toFixed(0)}%`
                            }
                        >
                            {pieData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                        </Pie>
                        <Tooltip />
                    </PieChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    ),
};

export const PieChartDonut: Story = {
    render: () => (
        <Card className="w-[400px]">
            <CardHeader>
                <CardTitle>Dokumentverteilung</CardTitle>
                <CardDescription>Donut-Darstellung</CardDescription>
            </CardHeader>
            <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                        <Pie
                            data={pieData}
                            cx="50%"
                            cy="50%"
                            innerRadius={60}
                            outerRadius={100}
                            paddingAngle={2}
                            dataKey="value"
                        >
                            {pieData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                        </Pie>
                        <Tooltip />
                        <Legend />
                    </PieChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    ),
};

// ==================== Waterfall Chart ====================

export const WaterfallChartDefault: Story = {
    render: () => (
        <div className="w-[700px]">
            <WaterfallChart
                data={waterfallData}
                title="Finanzbewegungen"
                description="Aufschlüsselung der Wertveränderungen"
                prefix="EUR "
                height={400}
            />
        </div>
    ),
};

export const WaterfallChartCustomColors: Story = {
    render: () => (
        <div className="w-[700px]">
            <WaterfallChart
                data={waterfallData}
                title="Mit benutzerdefinierten Farben"
                description="Angepasste Farbgebung"
                prefix="EUR "
                height={400}
                colors={{
                    positive: '#10b981',
                    negative: '#f59e0b',
                    total: '#8b5cf6',
                    subtotal: '#06b6d4',
                }}
            />
        </div>
    ),
};

// ==================== Dashboard Grid ====================

export const ChartDashboard: Story = {
    render: () => (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-[1200px]">
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-base">Monatstrend</CardTitle>
                </CardHeader>
                <CardContent>
                    <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={monthlyData.slice(0, 6)}>
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip />
                            <Line
                                type="monotone"
                                dataKey="dokumente"
                                stroke="#2563eb"
                                strokeWidth={2}
                                dot={false}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-base">Verteilung</CardTitle>
                </CardHeader>
                <CardContent>
                    <ResponsiveContainer width="100%" height={200}>
                        <PieChart>
                            <Pie
                                data={pieData.slice(0, 4)}
                                cx="50%"
                                cy="50%"
                                innerRadius={40}
                                outerRadius={70}
                                dataKey="value"
                            >
                                {pieData.slice(0, 4).map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                            </Pie>
                            <Tooltip />
                        </PieChart>
                    </ResponsiveContainer>
                </CardContent>
            </Card>

            <Card className="md:col-span-2">
                <CardHeader className="pb-2">
                    <CardTitle className="text-base">Jahresübersicht</CardTitle>
                </CardHeader>
                <CardContent>
                    <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={monthlyData}>
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip />
                            <Bar
                                dataKey="dokumente"
                                fill="#2563eb"
                                radius={[2, 2, 0, 0]}
                            />
                        </BarChart>
                    </ResponsiveContainer>
                </CardContent>
            </Card>
        </div>
    ),
};

// ==================== Dark Mode ====================

export const DarkMode: Story = {
    render: () => (
        <Card className="w-[600px]">
            <CardHeader>
                <CardTitle>Dark Mode Chart</CardTitle>
                <CardDescription>Chart im dunklen Modus</CardDescription>
            </CardHeader>
            <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={monthlyData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                        <XAxis dataKey="name" stroke="#9ca3af" />
                        <YAxis stroke="#9ca3af" />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: '#1f2937',
                                border: '1px solid #374151',
                                borderRadius: '8px',
                            }}
                        />
                        <Legend />
                        <Line
                            type="monotone"
                            dataKey="dokumente"
                            name="Hochgeladen"
                            stroke="#60a5fa"
                            strokeWidth={2}
                        />
                        <Line
                            type="monotone"
                            dataKey="verarbeitet"
                            name="Verarbeitet"
                            stroke="#34d399"
                            strokeWidth={2}
                        />
                    </LineChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    ),
    parameters: {
        backgrounds: { default: 'dark' },
    },
    decorators: [
        (Story) => (
            <div className="dark">
                <Story />
            </div>
        ),
    ],
};
