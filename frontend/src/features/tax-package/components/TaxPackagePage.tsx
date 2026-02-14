/**
 * Tax Package Page - Steuerberater-Paket Dashboard
 *
 * Zeigt Buchhaltungspakete und bietet Vollständigkeitsprüfung.
 * - Statistiken (Pakete, Dokumente, Completion Rate)
 * - Paket-Erstellung mit Zeitraum-Auswahl
 * - Vollständigkeitsprüfung mit Score und fehlenden Elementen
 * - Paket-Liste mit Aktionen (Generieren, Versenden, Herunterladen)
 * - Warnung bei fehlenden Dokumenten
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import {
  usePackages,
  usePackageStats,
  usePackageConfigurations,
  useCreatePackage,
  useGeneratePackage,
  useSendPackage,
  useCheckCompleteness,
} from '../hooks/use-tax-package';
import {
  AlertTriangle,
  CheckCircle2,
  Package,
  FileText,
  HardDrive,
  TrendingUp,
  Send,
  Download,
  Calendar,
  Sparkles,
  AlertCircle,
} from 'lucide-react';
import type { TaxPackage, CompletenessReport } from '../api/tax-package-api';

export function TaxPackagePage() {
  const [selectedPeriod, setSelectedPeriod] = useState('');
  const [selectedConfig, setSelectedConfig] = useState('');
  const [completenessYear, setCompletenessYear] = useState(new Date().getFullYear());
  const [completenessQuarter, setCompletenessQuarter] = useState<number | undefined>();
  const [completenessResult, setCompletenessResult] = useState<CompletenessReport | null>(null);

  const { data: stats, isLoading: statsLoading } = usePackageStats();
  const { data: packages, isLoading: packagesLoading, error } = usePackages();
  const { data: configs } = usePackageConfigurations();
  const createMutation = useCreatePackage();
  const generateMutation = useGeneratePackage();
  const sendMutation = useSendPackage();
  const checkMutation = useCheckCompleteness();

  const handleCreatePackage = () => {
    if (!selectedPeriod) return;

    createMutation.mutate({
      period: selectedPeriod,
      config_id: selectedConfig || undefined,
    });
  };

  const handleGeneratePackage = (packageId: string) => {
    generateMutation.mutate(packageId);
  };

  const handleSendPackage = (packageId: string) => {
    sendMutation.mutate({ packageId });
  };

  const handleCheckCompleteness = () => {
    checkMutation.mutate(
      { year: completenessYear, quarter: completenessQuarter },
      {
        onSuccess: (data) => {
          setCompletenessResult(data);
        },
      }
    );
  };

  const handleDownloadPackage = (packageId: string) => {
    // In production: trigger actual download
    window.open(`/api/v1/tax-advisor/packages/${packageId}/download?file_type=all`, '_blank');
  };

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden der Pakete. Bitte versuchen Sie es später erneut.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight font-display">Steuerberater-Paket</h2>
        <p className="text-muted-foreground mt-1">
          Automatische Buchhaltungspakete für Ihren Steuerberater
        </p>
      </div>

      {/* Statistics Overview */}
      <div className="grid gap-4 md:grid-cols-4">
        {statsLoading ? (
          <>
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader className="pb-2">
                  <Skeleton className="h-4 w-24" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-8 w-16" />
                </CardContent>
              </Card>
            ))}
          </>
        ) : stats ? (
          <>
            <StatCard
              icon={<Package className="h-4 w-4" />}
              title="Erstellte Pakete"
              value={stats.total_packages}
            />
            <StatCard
              icon={<FileText className="h-4 w-4" />}
              title="Gesamtdokumente"
              value={stats.total_documents}
            />
            <StatCard
              icon={<TrendingUp className="h-4 w-4" />}
              title="Completion Rate"
              value={`${stats.completion_rate}%`}
            />
            <StatCard
              icon={<HardDrive className="h-4 w-4" />}
              title="Größe"
              value={`${stats.total_size_mb} MB`}
            />
          </>
        ) : null}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Package Creation */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5" />
              Neues Paket erstellen
            </CardTitle>
            <CardDescription>Erstellen Sie ein Buchhaltungspaket für einen Zeitraum</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="period">Zeitraum</Label>
              <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
                <SelectTrigger id="period">
                  <SelectValue placeholder="Zeitraum auswählen" />
                </SelectTrigger>
                <SelectContent>
                  {generatePeriodOptions().map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="config">Konfiguration (optional)</Label>
              <Select value={selectedConfig} onValueChange={setSelectedConfig}>
                <SelectTrigger id="config">
                  <SelectValue placeholder="Konfiguration auswählen" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Keine Konfiguration</SelectItem>
                  {configs?.map((config) => (
                    <SelectItem key={config.id} value={config.id}>
                      {config.name} ({getFrequencyLabel(config.frequency)})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button
              onClick={handleCreatePackage}
              disabled={!selectedPeriod || createMutation.isPending}
              className="w-full"
            >
              {createMutation.isPending ? 'Wird erstellt...' : 'Paket erstellen'}
            </Button>
          </CardContent>
        </Card>

        {/* Completeness Check */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5" />
              Vollständigkeitsprüfung
            </CardTitle>
            <CardDescription>Prüfen Sie die Vollständigkeit Ihrer Dokumente</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="year">Jahr</Label>
                <Select
                  value={completenessYear.toString()}
                  onValueChange={(v) => setCompletenessYear(parseInt(v, 10))}
                >
                  <SelectTrigger id="year">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 11 }, (_, i) => new Date().getFullYear() - 5 + i).map(
                      (year) => (
                        <SelectItem key={year} value={year.toString()}>
                          {year}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="quarter">Quartal (optional)</Label>
                <Select
                  value={completenessQuarter?.toString() ?? 'all'}
                  onValueChange={(v) => setCompletenessQuarter(v === 'all' ? undefined : parseInt(v, 10))}
                >
                  <SelectTrigger id="quarter">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Ganzes Jahr</SelectItem>
                    <SelectItem value="1">Q1</SelectItem>
                    <SelectItem value="2">Q2</SelectItem>
                    <SelectItem value="3">Q3</SelectItem>
                    <SelectItem value="4">Q4</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Button
              onClick={handleCheckCompleteness}
              disabled={checkMutation.isPending}
              className="w-full"
            >
              {checkMutation.isPending ? 'Wird geprüft...' : 'Vollständigkeit prüfen'}
            </Button>

            {completenessResult && (
              <div className="space-y-3 pt-4 border-t">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Score</span>
                  <span className={`text-2xl font-bold ${getScoreColor(completenessResult.completeness_score)}`}>
                    {completenessResult.completeness_score.toFixed(1)}%
                  </span>
                </div>
                <Progress value={completenessResult.completeness_score} className="h-2" />
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>
                    {completenessResult.checks_passed} / {completenessResult.total_checks} Checks
                  </span>
                  <Badge variant={completenessResult.is_complete ? 'default' : 'destructive'}>
                    {completenessResult.is_complete ? 'Vollständig' : 'Unvollständig'}
                  </Badge>
                </div>

                {completenessResult.missing_items.length > 0 && (
                  <div className="space-y-2 pt-2 border-t">
                    <h4 className="text-sm font-semibold">Fehlende Elemente</h4>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {completenessResult.missing_items.map((item, idx) => (
                        <div key={idx} className="text-xs p-2 rounded border">
                          <div className="flex items-start justify-between gap-2">
                            <span className="font-medium">{item.category}</span>
                            <Badge variant="outline" className="text-xs">
                              {getSeverityLabel(item.severity)}
                            </Badge>
                          </div>
                          <p className="text-muted-foreground mt-1">{item.description}</p>
                          {item.suggestion && (
                            <p className="text-primary mt-1 text-xs">💡 {item.suggestion}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Package List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Erstellte Pakete
          </CardTitle>
          <CardDescription>Übersicht aller Buchhaltungspakete</CardDescription>
        </CardHeader>
        <CardContent>
          {packagesLoading ? (
            <div className="space-y-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : packages && packages.length > 0 ? (
            <div className="space-y-4">
              {packages.map((pkg) => (
                <PackageRow
                  key={pkg.id}
                  package={pkg}
                  onGenerate={handleGeneratePackage}
                  onSend={handleSendPackage}
                  onDownload={handleDownloadPackage}
                  isGenerating={generateMutation.isPending}
                  isSending={sendMutation.isPending}
                />
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <Package className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">Noch keine Pakete</h3>
              <p className="text-muted-foreground">
                Erstellen Sie Ihr erstes Buchhaltungspaket, um loszulegen.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ==================== Helper Components ====================

interface StatCardProps {
  icon: React.ReactNode;
  title: string;
  value: string | number;
}

function StatCard({ icon, title, value }: StatCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  );
}

interface PackageRowProps {
  package: TaxPackage;
  onGenerate: (id: string) => void;
  onSend: (id: string) => void;
  onDownload: (id: string) => void;
  isGenerating: boolean;
  isSending: boolean;
}

function PackageRow({
  package: pkg,
  onGenerate,
  onSend,
  onDownload,
  isGenerating,
  isSending,
}: PackageRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 p-4 rounded-lg border">
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-3">
          <h4 className="font-semibold">{pkg.period_label}</h4>
          <Badge variant={getStatusVariant(pkg.status)}>{getStatusLabel(pkg.status)}</Badge>
        </div>

        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <FileText className="h-3 w-3" />
            {pkg.document_count} Dokumente
          </span>
          <span className="flex items-center gap-1">
            <HardDrive className="h-3 w-3" />
            {(pkg.total_size_bytes / (1024 * 1024)).toFixed(2)} MB
          </span>
          <span className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            {new Date(pkg.created_at).toLocaleDateString('de-DE')}
          </span>
        </div>

        {pkg.missing_documents.length > 0 && (
          <Alert variant="destructive" className="py-2">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              {pkg.missing_documents.length} fehlende{' '}
              {pkg.missing_documents.length === 1 ? 'Dokument' : 'Dokumente'}
            </AlertDescription>
          </Alert>
        )}
      </div>

      <div className="flex items-center gap-2">
        {pkg.status === 'draft' && (
          <Button size="sm" variant="outline" onClick={() => onGenerate(pkg.id)} disabled={isGenerating}>
            <Sparkles className="h-4 w-4 mr-1" />
            Generieren
          </Button>
        )}

        {pkg.status === 'ready' && (
          <Button size="sm" onClick={() => onSend(pkg.id)} disabled={isSending}>
            <Send className="h-4 w-4 mr-1" />
            Versenden
          </Button>
        )}

        {(pkg.status === 'sent' || pkg.status === 'downloaded') && (
          <Button size="sm" variant="outline" onClick={() => onDownload(pkg.id)}>
            <Download className="h-4 w-4 mr-1" />
            Herunterladen
          </Button>
        )}
      </div>
    </div>
  );
}

// ==================== Helper Functions ====================

function getStatusVariant(
  status: string
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'sent':
      return 'default';
    case 'ready':
      return 'secondary';
    case 'draft':
      return 'outline';
    case 'downloaded':
      return 'default';
    case 'expired':
      return 'destructive';
    default:
      return 'outline';
  }
}

function getStatusLabel(status: string): string {
  switch (status) {
    case 'draft':
      return 'Entwurf';
    case 'ready':
      return 'Bereit';
    case 'sent':
      return 'Versendet';
    case 'downloaded':
      return 'Heruntergeladen';
    case 'expired':
      return 'Abgelaufen';
    default:
      return status;
  }
}

function getFrequencyLabel(frequency: string): string {
  switch (frequency) {
    case 'monthly':
      return 'Monatlich';
    case 'quarterly':
      return 'Quartalsweise';
    case 'yearly':
      return 'Jährlich';
    case 'on_demand':
      return 'Auf Anfrage';
    default:
      return frequency;
  }
}

function getSeverityLabel(severity: string): string {
  switch (severity) {
    case 'required':
      return 'Erforderlich';
    case 'recommended':
      return 'Empfohlen';
    case 'optional':
      return 'Optional';
    default:
      return severity;
  }
}

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  return 'text-red-600';
}

function generatePeriodOptions(): { value: string; label: string }[] {
  const options: { value: string; label: string }[] = [];
  const now = new Date();
  const currentYear = now.getFullYear();

  // Last 12 months
  for (let i = 0; i < 12; i++) {
    const date = new Date(currentYear, now.getMonth() - i, 1);
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    options.push({
      value: `${year}-${month}`,
      label: `${date.toLocaleDateString('de-DE', { month: 'long' })} ${year}`,
    });
  }

  // Last 4 quarters
  for (let i = 0; i < 4; i++) {
    const quarter = Math.floor((now.getMonth() - i * 3) / 3) + 1;
    const year = currentYear - Math.floor((now.getMonth() - i * 3) / 12);
    const q = ((quarter - 1 + 4) % 4) + 1;
    options.push({
      value: `${year}-Q${q}`,
      label: `Q${q} ${year}`,
    });
  }

  return options;
}
