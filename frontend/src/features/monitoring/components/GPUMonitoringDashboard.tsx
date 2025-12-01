import { useEffect, useState } from 'react';
import GaugeComponent from 'react-gauge-component';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Card } from '@/components/ui/card';
import { motion } from 'framer-motion';
import { motionTokens } from '@/lib/motion-tokens';

interface GPUMetrics {
    utilization: number;
    vramUsed: number;
    vramTotal: number;
    temperature: number;
    time: number;
}

const MotionDiv = motion.div as any;

export function GPUMonitoringDashboard() {
    // Mock WebSocket data for now
    const [gpuMetrics, setGpuMetrics] = useState<GPUMetrics | null>(null);
    const [history, setHistory] = useState<GPUMetrics[]>([]);

    useEffect(() => {
        const interval = setInterval(() => {
            const now = Date.now();
            const newMetrics: GPUMetrics = {
                utilization: Math.floor(Math.random() * 40) + 30, // 30-70%
                vramUsed: Math.floor(Math.random() * 4) + 8, // 8-12GB
                vramTotal: 24,
                temperature: Math.floor(Math.random() * 20) + 50, // 50-70C
                time: now
            };

            setGpuMetrics(newMetrics);
            setHistory(prev => [...prev.slice(-60), newMetrics]);
        }, 1000);

        return () => clearInterval(interval);
    }, []);

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* GPU Utilization Gauge */}
            <MotionDiv
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...motionTokens.spring.gentle, delay: 0.1 }}
            >
                <Card className="p-6 glass-card h-full">
                    <h3 className="text-lg font-display font-semibold mb-4">GPU Auslastung</h3>
                    <div className="flex justify-center">
                        <GaugeComponent
                            type="semicircle"
                            value={gpuMetrics?.utilization || 0}
                            minValue={0}
                            maxValue={100}
                            arc={{
                                width: 0.2,
                                padding: 0.02,
                                cornerRadius: 1,
                                subArcs: [
                                    { limit: 50, color: 'oklch(0.72 0.17 145)', showTick: true },
                                    { limit: 80, color: 'oklch(0.82 0.15 75)', showTick: true },
                                    { limit: 100, color: 'oklch(0.55 0.22 25)', showTick: true }
                                ]
                            }}
                            pointer={{ type: 'needle', elastic: true, animationDelay: 0 }}
                            labels={{
                                valueLabel: { formatTextValue: (v) => `${v}%`, style: { fontSize: 35, fill: 'var(--foreground)', textShadow: 'none' } },
                                tickLabels: { type: 'outer', defaultTickValueConfig: { formatTextValue: (v) => `${v}%`, style: { fontSize: 10, fill: 'var(--muted-foreground)' } } }
                            }}
                        />
                    </div>
                </Card>
            </MotionDiv>

            {/* VRAM Gauge */}
            <MotionDiv
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...motionTokens.spring.gentle, delay: 0.2 }}
            >
                <Card className="p-6 glass-card h-full">
                    <h3 className="text-lg font-display font-semibold mb-4">VRAM Nutzung</h3>
                    <div className="flex justify-center">
                        <GaugeComponent
                            type="semicircle"
                            value={gpuMetrics?.vramUsed || 0}
                            minValue={0}
                            maxValue={gpuMetrics?.vramTotal || 24}
                            arc={{
                                width: 0.2,
                                padding: 0.02,
                                cornerRadius: 1,
                                subArcs: [
                                    { limit: 16, color: 'oklch(0.72 0.17 145)', showTick: true },
                                    { limit: 20, color: 'oklch(0.82 0.15 75)', showTick: true },
                                    { limit: 24, color: 'oklch(0.55 0.22 25)', showTick: true }
                                ]
                            }}
                            pointer={{ type: 'needle', elastic: true, animationDelay: 0 }}
                            labels={{
                                valueLabel: { formatTextValue: (v) => `${v}GB`, style: { fontSize: 35, fill: 'var(--foreground)', textShadow: 'none' } },
                                tickLabels: { type: 'outer', defaultTickValueConfig: { formatTextValue: (v) => `${v}GB`, style: { fontSize: 10, fill: 'var(--muted-foreground)' } } }
                            }}
                        />
                    </div>
                </Card>
            </MotionDiv>

            {/* Temperature Gauge */}
            <MotionDiv
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...motionTokens.spring.gentle, delay: 0.3 }}
            >
                <Card className="p-6 glass-card h-full">
                    <h3 className="text-lg font-display font-semibold mb-4">Temperatur</h3>
                    <div className="flex justify-center">
                        <GaugeComponent
                            type="semicircle"
                            value={gpuMetrics?.temperature || 0}
                            minValue={30}
                            maxValue={100}
                            arc={{
                                width: 0.2,
                                padding: 0.02,
                                cornerRadius: 1,
                                subArcs: [
                                    { limit: 60, color: 'oklch(0.72 0.17 145)', showTick: true },
                                    { limit: 80, color: 'oklch(0.82 0.15 75)', showTick: true },
                                    { limit: 100, color: 'oklch(0.55 0.22 25)', showTick: true }
                                ]
                            }}
                            pointer={{ type: 'needle', elastic: true, animationDelay: 0 }}
                            labels={{
                                valueLabel: { formatTextValue: (v) => `${v}°C`, style: { fontSize: 35, fill: 'var(--foreground)', textShadow: 'none' } },
                                tickLabels: { type: 'outer', defaultTickValueConfig: { formatTextValue: (v) => `${v}°C`, style: { fontSize: 10, fill: 'var(--muted-foreground)' } } }
                            }}
                        />
                    </div>
                </Card>
            </MotionDiv>

            {/* Time Series Chart */}
            <MotionDiv
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...motionTokens.spring.gentle, delay: 0.4 }}
                className="col-span-1 md:col-span-3"
            >
                <Card className="p-6 glass-card">
                    <h3 className="text-lg font-display font-semibold mb-4">Verlauf (letzte 60 Sekunden)</h3>
                    <div className="h-[300px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={history}>
                                <defs>
                                    <linearGradient id="colorUtil" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="colorVram" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="var(--chart-2)" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="var(--chart-2)" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <XAxis
                                    dataKey="time"
                                    tickFormatter={(t) => new Date(t).toLocaleTimeString()}
                                    stroke="var(--muted-foreground)"
                                    fontSize={12}
                                    tickLine={false}
                                    axisLine={false}
                                />
                                <YAxis
                                    domain={[0, 100]}
                                    stroke="var(--muted-foreground)"
                                    fontSize={12}
                                    tickLine={false}
                                    axisLine={false}
                                    tickFormatter={(v) => `${v}%`}
                                />
                                <Tooltip
                                    contentStyle={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)', borderRadius: 'var(--radius)' }}
                                    itemStyle={{ color: 'var(--foreground)' }}
                                    labelStyle={{ color: 'var(--muted-foreground)' }}
                                    labelFormatter={(t) => new Date(t).toLocaleTimeString()}
                                />
                                <Area
                                    type="monotone"
                                    dataKey="utilization"
                                    stroke="var(--chart-1)"
                                    fillOpacity={1}
                                    fill="url(#colorUtil)"
                                    name="GPU %"
                                    strokeWidth={2}
                                />
                                <Area
                                    type="monotone"
                                    dataKey="vramUsed"
                                    stroke="var(--chart-2)"
                                    fillOpacity={1}
                                    fill="url(#colorVram)"
                                    name="VRAM (GB)"
                                    strokeWidth={2}
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </Card>
            </MotionDiv>
        </div>
    );
}
