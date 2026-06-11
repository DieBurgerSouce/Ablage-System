/**
 * AI Decision Dashboard - Hauptübersicht
 *
 * Zeigt AI/ML Entscheidungen, Drift Status, Experimente
 * und Lernfortschritt in einer kompakten Übersicht.
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, TrendingUp, CheckCircle2, Clock, Settings2, BarChart3, FlaskConical } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import {
  useAIDecisionStats,
  useDriftStatus,
  useLearningStats,
  useMetricsSummary,
  useExperiments,
} from '../hooks/useAIDecisions';
import { AIDecisionList } from './AIDecisionList';
import { AIThresholdSettings } from './AIThresholdSettings';
import { AILearningStats } from './AILearningStats';
import { DriftStatusCard } from './DriftStatusCard';
import { ExperimentsPanel } from './ExperimentsPanel';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export function AIDecisionDashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const { data: stats, isLoading: statsLoading } = useAIDecisionStats();
  const { data: driftStatus } = useDriftStatus();
  const { data: learningStats } = useLearningStats();
  const { data: metrics } = useMetricsSummary();
  const { data: experiments } = useExperiments('running');

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-6 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Brain className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">AI Entscheidungen</h1>
              <p className="text-muted-foreground">
                OCR-Routing, Drift Detection und ML-Optimierung
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="gap-1">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              ML Aktiv
            </Badge>
            {experiments && experiments.length > 0 && (
              <Badge variant="secondary" className="gap-1">
                <FlaskConical className="w-3 h-3" />
                {experiments.length} Experimente
              </Badge>
            )}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto p-6">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="overview" className="gap-2">
              <BarChart3 className="w-4 h-4" />
              Übersicht
            </TabsTrigger>
            <TabsTrigger value="decisions" className="gap-2">
              <Brain className="w-4 h-4" />
              Entscheidungen
            </TabsTrigger>
            <TabsTrigger value="experiments" className="gap-2">
              <FlaskConical className="w-4 h-4" />
              Experimente
            </TabsTrigger>
            <TabsTrigger value="settings" className="gap-2">
              <Settings2 className="w-4 h-4" />
              Einstellungen
            </TabsTrigger>
          </TabsList>

          <AnimatePresence mode="wait">
            <TabsContent value="overview" className="mt-0">
              <OverviewTab
                stats={stats}
                statsLoading={statsLoading}
                driftStatus={driftStatus}
                learningStats={learningStats}
                metrics={metrics}
              />
            </TabsContent>

            <TabsContent value="decisions" className="mt-0">
              <AIDecisionList />
            </TabsContent>

            <TabsContent value="experiments" className="mt-0">
              <ExperimentsPanel />
            </TabsContent>

            <TabsContent value="settings" className="mt-0">
              <div className="grid gap-6 lg:grid-cols-2">
                <AIThresholdSettings />
                <AILearningStats />
              </div>
            </TabsContent>
          </AnimatePresence>
        </Tabs>
      </div>
    </div>
  );
}

interface OverviewTabProps {
  stats: ReturnType<typeof useAIDecisionStats>['data'];
  statsLoading: boolean;
  driftStatus: ReturnType<typeof useDriftStatus>['data'];
  learningStats: ReturnType<typeof useLearningStats>['data'];
  metrics: ReturnType<typeof useMetricsSummary>['data'];
}

function OverviewTab({
  stats,
  statsLoading,
  driftStatus,
  learningStats,
  metrics,
}: OverviewTabProps) {
  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-6"
    >
      {/* Stats Cards */}
      <motion.div variants={itemVariants} className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Gesamt Entscheidungen"
          value={stats?.total_decisions ?? 0}
          icon={Brain}
          loading={statsLoading}
        />
        <StatsCard
          title="Zur Prüfung"
          value={stats?.pending_review ?? 0}
          icon={Clock}
          variant={stats?.pending_review ? 'warning' : 'default'}
          loading={statsLoading}
        />
        <StatsCard
          title="Durchschnittliche Konfidenz"
          value={stats ? `${(stats.avg_confidence * 100).toFixed(1)}%` : '0%'}
          icon={TrendingUp}
          loading={statsLoading}
        />
        <StatsCard
          title="Korrigiert"
          value={stats?.corrected ?? 0}
          icon={CheckCircle2}
          variant="success"
          loading={statsLoading}
        />
      </motion.div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Decision Distribution */}
        <motion.div variants={itemVariants}>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Entscheidungs-Verteilung</CardTitle>
              <CardDescription>Nach Konfidenz-Level</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {stats?.by_confidence_level && (
                  <>
                    <ConfidenceBar
                      label="Sehr Hoch"
                      count={stats.by_confidence_level.very_high}
                      total={stats.total_decisions}
                      color="bg-green-500"
                    />
                    <ConfidenceBar
                      label="Hoch"
                      count={stats.by_confidence_level.high}
                      total={stats.total_decisions}
                      color="bg-emerald-500"
                    />
                    <ConfidenceBar
                      label="Mittel"
                      count={stats.by_confidence_level.medium}
                      total={stats.total_decisions}
                      color="bg-yellow-500"
                    />
                    <ConfidenceBar
                      label="Niedrig"
                      count={stats.by_confidence_level.low}
                      total={stats.total_decisions}
                      color="bg-orange-500"
                    />
                    <ConfidenceBar
                      label="Sehr Niedrig"
                      count={stats.by_confidence_level.very_low}
                      total={stats.total_decisions}
                      color="bg-red-500"
                    />
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Backend Usage */}
        <motion.div variants={itemVariants}>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Backend-Nutzung</CardTitle>
              <CardDescription>OCR-Engine Verteilung</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {stats?.by_backend &&
                  Object.entries(stats.by_backend).map(([backend, count]) => (
                    <BackendBar
                      key={backend}
                      backend={backend}
                      count={count}
                      total={stats.total_decisions}
                    />
                  ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Drift Status */}
        <motion.div variants={itemVariants}>
          <DriftStatusCard driftStatus={driftStatus} />
        </motion.div>

        {/* Learning Progress */}
        <motion.div variants={itemVariants}>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Lernfortschritt</CardTitle>
              <CardDescription>Modell-Optimierung durch Korrekturen</CardDescription>
            </CardHeader>
            <CardContent>
              {learningStats && (
                <div className="space-y-4">
                  <div className="flex justify-between text-sm">
                    <span>Genauigkeit vor Training</span>
                    <span className="font-medium">
                      {(learningStats.model_accuracy_before * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span>Genauigkeit nach Training</span>
                    <span className="font-medium text-green-600">
                      {(learningStats.model_accuracy_after * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="pt-2 border-t">
                    <div className="flex items-center gap-2 text-sm">
                      <TrendingUp className="w-4 h-4 text-green-500" />
                      <span className="font-medium text-green-600">
                        +{learningStats.improvement_percent.toFixed(1)}% Verbesserung
                      </span>
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {learningStats.total_corrections} Korrekturen,{' '}
                    {learningStats.corrections_applied} angewendet
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </motion.div>
  );
}

interface StatsCardProps {
  title: string;
  value: string | number;
  icon: React.ElementType;
  variant?: 'default' | 'success' | 'warning' | 'error';
  loading?: boolean;
}

function StatsCard({
  title,
  value,
  icon: Icon,
  variant = 'default',
  loading,
}: StatsCardProps) {
  const variantStyles = {
    default: 'bg-primary/10 text-primary',
    success: 'bg-green-500/10 text-green-600',
    warning: 'bg-yellow-500/10 text-yellow-600',
    error: 'bg-red-500/10 text-red-600',
  };

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center gap-4">
          <div className={cn('p-3 rounded-lg', variantStyles[variant])}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold">
              {loading ? (
                <span className="inline-block w-16 h-8 bg-muted animate-pulse rounded" />
              ) : (
                value
              )}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface ConfidenceBarProps {
  label: string;
  count: number;
  total: number;
  color: string;
}

function ConfidenceBar({ label, count, total, color }: ConfidenceBarProps) {
  const percentage = total > 0 ? (count / total) * 100 : 0;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted-foreground">
          {count} ({percentage.toFixed(1)}%)
        </span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <motion.div
          className={cn('h-full rounded-full', color)}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

interface BackendBarProps {
  backend: string;
  count: number;
  total: number;
}

function BackendBar({ backend, count, total }: BackendBarProps) {
  const percentage = total > 0 ? (count / total) * 100 : 0;

  const backendColors: Record<string, string> = {
    'deepseek-janus-pro': 'bg-purple-500',
    'got-ocr-2.0': 'bg-blue-500',
    'surya-gpu': 'bg-cyan-500',
    surya: 'bg-slate-500',
  };

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="font-mono text-xs">{backend}</span>
        <span className="text-muted-foreground">
          {count} ({percentage.toFixed(1)}%)
        </span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <motion.div
          className={cn('h-full rounded-full', backendColors[backend] ?? 'bg-primary')}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}
