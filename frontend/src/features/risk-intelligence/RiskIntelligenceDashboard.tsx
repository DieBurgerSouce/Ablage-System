/**
 * Risk Intelligence Dashboard
 *
 * Hauptseite für erweiterte Risikoanalyse mit Branchen-Benchmarks,
 * Trends und Netzwerk-Analyse.
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Search, RefreshCw, Gauge, TrendingUp, Building2, PieChart, AlertCircle } from 'lucide-react';
import {
  usePortfolioRisk,
  useEntityRiskProfile,
  useIndustryBenchmarks,
  useRefreshRiskProfile,
} from './hooks/use-risk-intelligence';
import { RiskScoreGauge } from './components/RiskScoreGauge';
import { TrendChart } from './components/TrendChart';
import { BenchmarkComparison } from './components/BenchmarkComparison';
import { NetworkGraph } from './components/NetworkGraph';
import { PortfolioOverview } from './components/PortfolioOverview';
import { RecommendationsList } from './components/RecommendationsList';
import type { RiskProfile } from './api/risk-intelligence-api';

export function RiskIntelligenceDashboard() {
  const [activeTab, setActiveTab] = useState('portfolio');
  const [entityFilter, setEntityFilter] = useState<'all' | 'customer' | 'supplier'>('all');
  const [selectedEntityId, setSelectedEntityId] = useState<string>('');
  const [searchInput, setSearchInput] = useState('');

  // Queries
  const { data: portfolio, isLoading: portfolioLoading, error: portfolioError } = usePortfolioRisk(
    entityFilter === 'all' ? undefined : entityFilter
  );
  const { data: benchmarks } = useIndustryBenchmarks();
  const {
    data: riskProfile,
    isLoading: profileLoading,
    error: profileError,
  } = useEntityRiskProfile(selectedEntityId || undefined);
  const refreshProfile = useRefreshRiskProfile();

  const handleSearch = () => {
    if (searchInput.trim()) {
      setSelectedEntityId(searchInput.trim());
      setActiveTab('entity');
    }
  };


  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Gauge className="w-6 h-6 text-primary" />
            Risk Intelligence
          </h1>
          <p className="text-muted-foreground">
            Erweiterte Risikoanalyse mit Branchen-Benchmarks, Trends und Netzwerk-Analyse
          </p>
        </div>

        {/* Search */}
        <div className="flex gap-2">
          <Input
            placeholder="Entity-ID eingeben..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="w-64"
          />
          <Button onClick={handleSearch} disabled={!searchInput.trim()}>
            <Search className="w-4 h-4 mr-2" />
            Analysieren
          </Button>
        </div>
      </div>

      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid grid-cols-3 w-full max-w-md">
          <TabsTrigger value="portfolio" className="gap-2">
            <PieChart className="w-4 h-4" />
            Portfolio
          </TabsTrigger>
          <TabsTrigger value="entity" className="gap-2" disabled={!selectedEntityId}>
            <Gauge className="w-4 h-4" />
            Entity
          </TabsTrigger>
          <TabsTrigger value="benchmarks" className="gap-2">
            <Building2 className="w-4 h-4" />
            Benchmarks
          </TabsTrigger>
        </TabsList>

        {/* Portfolio Tab */}
        <TabsContent value="portfolio" className="space-y-6">
          <div className="flex items-center gap-4">
            <Select
              value={entityFilter}
              onValueChange={(v) => setEntityFilter(v as typeof entityFilter)}
            >
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Filter" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Entities</SelectItem>
                <SelectItem value="customer">Nur Kunden</SelectItem>
                <SelectItem value="supplier">Nur Lieferanten</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {portfolioLoading ? (
            <PortfolioSkeleton />
          ) : portfolioError ? (
            <Alert variant="destructive">
              <AlertCircle className="w-4 h-4" />
              <AlertTitle>Fehler</AlertTitle>
              <AlertDescription>
                Portfolio-Daten konnten nicht geladen werden.
              </AlertDescription>
            </Alert>
          ) : portfolio ? (
            <PortfolioOverview
              portfolio={portfolio}
              // onEntitySelect={handleEntitySelect}
            />
          ) : null}
        </TabsContent>

        {/* Entity Tab */}
        <TabsContent value="entity" className="space-y-6">
          {!selectedEntityId ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Search className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                <p className="text-muted-foreground">
                  Geben Sie eine Entity-ID ein oder wählen Sie eine Entity aus dem Portfolio.
                </p>
              </CardContent>
            </Card>
          ) : profileLoading ? (
            <EntitySkeleton />
          ) : profileError ? (
            <Alert variant="destructive">
              <AlertCircle className="w-4 h-4" />
              <AlertTitle>Fehler</AlertTitle>
              <AlertDescription>
                Risikoprofil konnte nicht geladen werden. Prüfen Sie die Entity-ID.
              </AlertDescription>
            </Alert>
          ) : riskProfile ? (
            <EntityProfile
              profile={riskProfile}
              onRefresh={() => refreshProfile.mutate(selectedEntityId)}
              isRefreshing={refreshProfile.isPending}
            />
          ) : null}
        </TabsContent>

        {/* Benchmarks Tab */}
        <TabsContent value="benchmarks" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Branchen-Benchmarks</CardTitle>
              <CardDescription>
                Vergleichswerte für verschiedene Branchen
              </CardDescription>
            </CardHeader>
            <CardContent>
              {benchmarks ? (
                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {benchmarks.map((b) => (
                    <Card key={b.industry} className="bg-muted/50">
                      <CardContent className="pt-6">
                        <h3 className="font-semibold capitalize mb-4">
                          {b.industry === 'retail'
                            ? 'Einzelhandel'
                            : b.industry === 'manufacturing'
                            ? 'Fertigung'
                            : b.industry === 'services'
                            ? 'Dienstleistungen'
                            : b.industry === 'construction'
                            ? 'Bauwesen'
                            : b.industry === 'technology'
                            ? 'Technologie'
                            : b.industry}
                        </h3>
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">
                              Durchschn. Zahlungsverzögerung
                            </span>
                            <span className="font-medium">{b.avg_payment_delay} Tage</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Ausfallrate</span>
                            <span className="font-medium">
                              {(b.default_rate * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Risikofaktor</span>
                            <span className="font-medium">{b.industry_risk_factor.toFixed(1)}x</span>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  Benchmark-Daten werden geladen...
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// Entity Profile Sub-Component
function EntityProfile({
  profile,
  onRefresh,
  isRefreshing,
}: {
  profile: RiskProfile;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  return (
    <div className="space-y-6">
      {/* Header Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-xl">{profile.entity_name}</CardTitle>
              <CardDescription>
                {profile.entity_type === 'customer' ? 'Kunde' : 'Lieferant'} | {profile.industry}
              </CardDescription>
            </div>
            <div className="flex items-center gap-4">
              <RiskScoreGauge score={profile.overall_risk_score} size="md" />
              <Button variant="outline" onClick={onRefresh} disabled={isRefreshing}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
                Aktualisieren
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Analysis Grid */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Trend Analysis */}
        {profile.analysis.trend && (
          <TrendChart trend={profile.analysis.trend} />
        )}

        {/* Benchmark Comparison */}
        {profile.analysis.benchmark && (
          <BenchmarkComparison benchmark={profile.analysis.benchmark} />
        )}

        {/* Network Analysis */}
        {profile.analysis.network && (
          <NetworkGraph network={profile.analysis.network} />
        )}

        {/* Recommendations */}
        <RecommendationsList recommendations={profile.recommendations} />
      </div>

      {/* Internal Analysis Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            Interne Analyse
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Basis-Score</p>
              <p className="text-2xl font-bold">
                {profile.analysis.internal.base_score.toFixed(0)}
              </p>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Zahlungsverzögerung</p>
              <p className="text-2xl font-bold">
                {profile.analysis.internal.payment_delay_avg.toFixed(0)} Tage
              </p>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Ausfallrate</p>
              <p className="text-2xl font-bold">
                {(profile.analysis.internal.default_rate * 100).toFixed(1)}%
              </p>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Rechnungen gesamt</p>
              <p className="text-2xl font-bold">{profile.analysis.internal.total_invoices}</p>
            </div>
            <div className="text-center p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Überfällig</p>
              <p className="text-2xl font-bold text-orange-500">
                {profile.analysis.internal.overdue_invoices}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Skeleton Components
function PortfolioSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <Skeleton className="h-4 w-20 mb-2" />
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-64 w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-64 w-full" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function EntitySkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <Skeleton className="h-6 w-48 mb-2" />
              <Skeleton className="h-4 w-32" />
            </div>
            <Skeleton className="h-24 w-36" />
          </div>
        </CardHeader>
      </Card>
      <div className="grid md:grid-cols-2 gap-6">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-40" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-48 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
