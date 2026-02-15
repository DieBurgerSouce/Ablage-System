/**
 * KIPipelinePage
 * Main page with tabs: Übersicht | Konfidenz | Preisabweichungen
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Brain,
  TrendingUp,
  AlertTriangle,
  FileText,
  Target,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  useStatistics,
  useFieldAccuracy,
  usePriceDeviations,
} from '../hooks/use-ki-pipeline-queries';
import { PriceDeviationAlert } from '../components/PriceDeviationAlert';
import { FIELD_LABELS } from '../types/ki-pipeline-types';

export function KIPipelinePage() {
  const [activeTab, setActiveTab] = useState('overview');
  const { data: stats, isLoading: statsLoading } = useStatistics();
  const { data: fieldAccuracy, isLoading: accuracyLoading } =
    useFieldAccuracy();
  const { data: deviations, isLoading: deviationsLoading } =
    usePriceDeviations({ limit: 10 });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <Brain className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">KI-Pipeline</h1>
            <p className="text-muted-foreground">
              Intelligente Dokumentenanalyse und Lernprozesse
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="overview" className="gap-2">
            <FileText className="h-4 w-4" />
            Übersicht
          </TabsTrigger>
          <TabsTrigger value="accuracy" className="gap-2">
            <Target className="h-4 w-4" />
            Konfidenz
          </TabsTrigger>
          <TabsTrigger value="deviations" className="gap-2">
            <AlertTriangle className="h-4 w-4" />
            Preisabweichungen
            {deviations && deviations.length > 0 && (
              <Badge variant="destructive" className="ml-1">
                {deviations.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          {statsLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-32" />
              ))}
            </div>
          ) : stats ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard
                  title="Verarbeitete Dokumente"
                  value={stats.total_documents_processed.toLocaleString('de-DE')}
                  icon={<FileText className="h-5 w-5" />}
                  color="blue"
                />
                <StatCard
                  title="Durchschn. Konfidenz"
                  value={`${Math.round(stats.avg_confidence_score * 100)}%`}
                  icon={<TrendingUp className="h-5 w-5" />}
                  color="green"
                />
                <StatCard
                  title="Lernprofile"
                  value={stats.learning_profiles_count.toLocaleString('de-DE')}
                  icon={<Brain className="h-5 w-5" />}
                  color="purple"
                />
                <StatCard
                  title="Hohe Konfidenz"
                  value={`${Math.round(stats.high_confidence_fields_percent)}%`}
                  icon={<Check className="h-5 w-5" />}
                  color="emerald"
                  subtitle="Felder >90%"
                />
              </div>

              {/* Recent Deviations */}
              {deviations && deviations.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <AlertTriangle className="h-5 w-5" />
                      Aktuelle Preisabweichungen
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {deviations.slice(0, 3).map((deviation) => (
                      <PriceDeviationAlert
                        key={deviation.document_id}
                        deviation={deviation}
                        variant="banner"
                      />
                    ))}
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Keine Statistiken verfügbar
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Accuracy Tab */}
        <TabsContent value="accuracy" className="space-y-6">
          {accuracyLoading ? (
            <Skeleton className="h-96" />
          ) : fieldAccuracy && fieldAccuracy.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Target className="h-5 w-5" />
                  Feldgenauigkeit
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {fieldAccuracy
                    .sort((a, b) => b.accuracy - a.accuracy)
                    .map((field) => {
                      const percent = Math.round(field.accuracy * 100);
                      const fieldLabel =
                        FIELD_LABELS[field.field] || field.field;

                      return (
                        <div
                          key={field.field}
                          className="flex items-center gap-4"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-sm font-medium truncate">
                                {fieldLabel}
                              </span>
                              <Badge
                                variant={
                                  percent >= 90 ? 'default' : 'secondary'
                                }
                                className={cn(
                                  percent >= 90 && 'bg-green-500',
                                  percent >= 60 &&
                                    percent < 90 &&
                                    'bg-yellow-500 text-white',
                                  percent < 60 && 'bg-red-500 text-white'
                                )}
                              >
                                {percent}%
                              </Badge>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {field.sample_count.toLocaleString('de-DE')}{' '}
                              Stichproben
                            </div>
                          </div>
                        </div>
                      );
                    })}
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Keine Genauigkeitsdaten verfügbar
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Deviations Tab */}
        <TabsContent value="deviations" className="space-y-6">
          {deviationsLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-32" />
              ))}
            </div>
          ) : deviations && deviations.length > 0 ? (
            <div className="space-y-4">
              {deviations.map((deviation) => (
                <PriceDeviationAlert
                  key={deviation.document_id}
                  deviation={deviation}
                  variant="card"
                />
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Keine Preisabweichungen gefunden
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// Stat Card Component
interface StatCardProps {
  title: string;
  value: string;
  icon: React.ReactNode;
  color: 'blue' | 'green' | 'purple' | 'emerald';
  subtitle?: string;
}

function StatCard({ title, value, icon, color, subtitle }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
    green: 'bg-green-500/10 text-green-600 dark:text-green-400',
    purple: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
    emerald: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold">{value}</p>
            {subtitle && (
              <p className="text-xs text-muted-foreground">{subtitle}</p>
            )}
          </div>
          <div className={cn('p-3 rounded-lg', colorClasses[color])}>
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
