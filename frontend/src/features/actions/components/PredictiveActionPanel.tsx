/**
 * Predictive Action Panel Komponente
 *
 * Zeigt proaktive Handlungsvorschlaege mit:
 * - Kritische Aktionen (Mahnung, Skonto)
 * - Akzeptieren/Ablehnen/Verschieben
 * - Confidence-Anzeige
 * - Benefit-Text (z.B. "Spart 245€ Skonto")
 *
 * Phase 2.2 der Feature-Roadmap (Januar 2026)
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useCriticalActions,
  useSkontoActions,
  useDunningActions,
  useActionStatistics,
  useAcceptAction,
  useRejectAction,
  useSnoozeAction,
} from '../hooks/use-predictive-actions';
import type {
  PredictiveAction,
  ActionPriority,
  ActionsSummary,
  ActionStatistics,
} from '@/lib/api/services/predictive-actions';
import {
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Clock,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  ChevronRight,
  Bell,
  Percent,
  Receipt,
  Phone,
  Calendar,
  X,
  Pause,
  Check,
  Info,
  Sparkles,
  Target,
  CircleDollarSign,
} from 'lucide-react';

// ==================== Utility Functions ====================

function formatCurrency(value: number, currency = 'EUR'): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value / 100);
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateStr));
}

function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Heute';
  if (diffDays === 1) return 'Morgen';
  if (diffDays === -1) return 'Gestern';
  if (diffDays > 0 && diffDays <= 7) return `In ${diffDays} Tagen`;
  if (diffDays < 0 && diffDays >= -7) return `Vor ${Math.abs(diffDays)} Tagen`;
  return formatDate(dateStr);
}

// ==================== Priority Config ====================

const PRIORITY_CONFIG: Record<
  ActionPriority,
  {
    label: string;
    icon: typeof AlertTriangle;
    color: string;
    bgColor: string;
    borderColor: string;
    textColor: string;
  }
> = {
  critical: {
    label: 'Kritisch',
    icon: AlertTriangle,
    color: '#ef4444',
    bgColor: 'bg-red-50 dark:bg-red-950',
    borderColor: 'border-red-200 dark:border-red-800',
    textColor: 'text-red-700 dark:text-red-400',
  },
  high: {
    label: 'Hoch',
    icon: AlertCircle,
    color: '#f97316',
    bgColor: 'bg-orange-50 dark:bg-orange-950',
    borderColor: 'border-orange-200 dark:border-orange-800',
    textColor: 'text-orange-700 dark:text-orange-400',
  },
  medium: {
    label: 'Mittel',
    icon: Info,
    color: '#eab308',
    bgColor: 'bg-yellow-50 dark:bg-yellow-950',
    borderColor: 'border-yellow-200 dark:border-yellow-800',
    textColor: 'text-yellow-700 dark:text-yellow-400',
  },
  low: {
    label: 'Niedrig',
    icon: CheckCircle2,
    color: '#22c55e',
    bgColor: 'bg-green-50 dark:bg-green-950',
    borderColor: 'border-green-200 dark:border-green-800',
    textColor: 'text-green-700 dark:text-green-400',
  },
};

const ACTION_TYPE_ICONS: Record<string, typeof Receipt> = {
  send_dunning: Receipt,
  call_customer: Phone,
  use_skonto: Percent,
  pay_invoice: CircleDollarSign,
  renew_contract: Calendar,
  cancel_contract: X,
  adjust_budget: Target,
  review_budget: TrendingUp,
  schedule_payment: Clock,
  check_payment: Check,
  custom: Sparkles,
};

// ==================== Priority Badge Component ====================

function PriorityBadge({ priority }: { priority: ActionPriority }) {
  const config = PRIORITY_CONFIG[priority];
  const Icon = config.icon;

  return (
    <Badge
      variant="outline"
      className={`${config.bgColor} ${config.borderColor} ${config.textColor} gap-1`}
    >
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  );
}

// ==================== Confidence Bar Component ====================

function ConfidenceBar({ confidence }: { confidence: number }) {
  const getColor = () => {
    if (confidence >= 90) return 'bg-green-500';
    if (confidence >= 70) return 'bg-lime-500';
    if (confidence >= 50) return 'bg-yellow-500';
    return 'bg-orange-500';
  };

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">Confidence</span>
        <span>{formatPercent(confidence)}</span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full ${getColor()} rounded-full transition-all`}
          style={{ width: `${confidence}%` }}
        />
      </div>
    </div>
  );
}

// ==================== Summary Card Component ====================

interface SummaryCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  variant?: 'default' | 'warning' | 'success';
}

function SummaryCard({
  title,
  value,
  subtitle,
  icon,
  variant = 'default',
}: SummaryCardProps) {
  const variantClasses = {
    default: '',
    warning: 'border-orange-200 dark:border-orange-800',
    success: 'border-green-200 dark:border-green-800',
  };

  return (
    <Card className={variantClasses[variant]}>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground">{title}</p>
            <p className="text-xl font-bold">{value}</p>
            {subtitle && (
              <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>
            )}
          </div>
          <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center">
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Action Card Component ====================

interface ActionCardProps {
  action: PredictiveAction;
  onAccept: (executeImmediately?: boolean) => void;
  onReject: (reason?: string) => void;
  onSnooze: (hours?: number) => void;
  isLoading?: boolean;
}

function ActionCard({
  action,
  onAccept,
  onReject,
  onSnooze,
  isLoading,
}: ActionCardProps) {
  const [showRejectDialog, setShowRejectDialog] = useState(false);
  const [showSnoozeDialog, setShowSnoozeDialog] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [snoozeHours, setSnoozeHours] = useState('24');

  const config = PRIORITY_CONFIG[action.priority];
  const ActionIcon = ACTION_TYPE_ICONS[action.actionType] || Sparkles;

  const handleReject = () => {
    onReject(rejectReason || undefined);
    setShowRejectDialog(false);
    setRejectReason('');
  };

  const handleSnooze = () => {
    onSnooze(parseInt(snoozeHours, 10));
    setShowSnoozeDialog(false);
  };

  return (
    <>
      <Card className={`${config.borderColor} border-l-4`}>
        <CardContent className="pt-4">
          <div className="flex items-start justify-between gap-4">
            {/* Left: Icon and Content */}
            <div className="flex items-start gap-3 flex-1 min-w-0">
              <div
                className={`h-10 w-10 rounded-lg ${config.bgColor} flex items-center justify-center flex-shrink-0`}
              >
                <ActionIcon className={`h-5 w-5 ${config.textColor}`} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h4 className="font-medium truncate">{action.title}</h4>
                  <PriorityBadge priority={action.priority} />
                </div>
                <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                  {action.description}
                </p>

                {/* Benefit Text */}
                {action.benefitText && (
                  <div className="mt-2 flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400">
                    <TrendingUp className="h-4 w-4" />
                    <span className="font-medium">{action.benefitText}</span>
                  </div>
                )}

                {/* Metadata */}
                <div className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground">
                  {action.metadata.invoiceNumber && (
                    <span className="flex items-center gap-1">
                      <Receipt className="h-3 w-3" />
                      {action.metadata.invoiceNumber}
                    </span>
                  )}
                  {action.metadata.amount && (
                    <span className="flex items-center gap-1">
                      <CircleDollarSign className="h-3 w-3" />
                      {formatCurrency(action.metadata.amount)}
                    </span>
                  )}
                  {action.deadline && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatRelativeTime(action.deadline)}
                    </span>
                  )}
                  {action.metadata.daysOverdue !== undefined &&
                    action.metadata.daysOverdue > 0 && (
                      <span className="flex items-center gap-1 text-red-600">
                        <AlertTriangle className="h-3 w-3" />
                        {action.metadata.daysOverdue} Tage ueberfaellig
                      </span>
                    )}
                </div>

                {/* Confidence */}
                <div className="mt-3 max-w-[200px]">
                  <ConfidenceBar confidence={action.confidence} />
                </div>
              </div>
            </div>

            {/* Right: Actions */}
            <div className="flex flex-col gap-2 flex-shrink-0">
              <Button
                size="sm"
                onClick={() => onAccept(false)}
                disabled={isLoading}
                className="w-24"
              >
                {isLoading ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Check className="h-4 w-4 mr-1" />
                    Annehmen
                  </>
                )}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowSnoozeDialog(true)}
                disabled={isLoading}
                className="w-24"
              >
                <Pause className="h-4 w-4 mr-1" />
                Spaeter
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowRejectDialog(true)}
                disabled={isLoading}
                className="w-24 text-muted-foreground hover:text-destructive"
              >
                <X className="h-4 w-4 mr-1" />
                Ablehnen
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Reject Dialog */}
      <Dialog open={showRejectDialog} onOpenChange={setShowRejectDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Aktion ablehnen</DialogTitle>
            <DialogDescription>
              Moechten Sie diese Aktion wirklich ablehnen? Optional koennen Sie
              einen Grund angeben.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="reject-reason">Grund (optional)</Label>
              <Textarea
                id="reject-reason"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="z.B. Bereits manuell erledigt, Nicht relevant, etc."
                className="mt-1.5"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowRejectDialog(false)}>
              Abbrechen
            </Button>
            <Button variant="destructive" onClick={handleReject}>
              Ablehnen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Snooze Dialog */}
      <Dialog open={showSnoozeDialog} onOpenChange={setShowSnoozeDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Aktion verschieben</DialogTitle>
            <DialogDescription>
              Fuer wie lange moechten Sie diese Aktion verschieben?
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="snooze-hours">Zeitraum</Label>
              <Select value={snoozeHours} onValueChange={setSnoozeHours}>
                <SelectTrigger className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 Stunde</SelectItem>
                  <SelectItem value="4">4 Stunden</SelectItem>
                  <SelectItem value="24">1 Tag</SelectItem>
                  <SelectItem value="72">3 Tage</SelectItem>
                  <SelectItem value="168">1 Woche</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSnoozeDialog(false)}>
              Abbrechen
            </Button>
            <Button onClick={handleSnooze}>
              <Clock className="h-4 w-4 mr-2" />
              Verschieben
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ==================== Actions List Component ====================

interface ActionsListProps {
  actions: PredictiveAction[];
  onAccept: (actionId: string, executeImmediately?: boolean) => void;
  onReject: (actionId: string, reason?: string) => void;
  onSnooze: (actionId: string, hours?: number) => void;
  loadingActionId?: string | null;
}

function ActionsList({
  actions,
  onAccept,
  onReject,
  onSnooze,
  loadingActionId,
}: ActionsListProps) {
  if (actions.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <CheckCircle2 className="h-12 w-12 mx-auto mb-4 text-green-500" />
        <p className="text-lg font-medium">Keine offenen Aktionen</p>
        <p className="text-sm">Alle Handlungsvorschlaege wurden bearbeitet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {actions.map((action) => (
        <ActionCard
          key={action.id}
          action={action}
          onAccept={(executeImmediately) => onAccept(action.id, executeImmediately)}
          onReject={(reason) => onReject(action.id, reason)}
          onSnooze={(hours) => onSnooze(action.id, hours)}
          isLoading={loadingActionId === action.id}
        />
      ))}
    </div>
  );
}

// ==================== Statistics Panel Component ====================

function StatisticsPanel({ stats }: { stats: ActionStatistics }) {
  const acceptanceRateColor =
    stats.acceptanceRate >= 70
      ? 'text-green-600'
      : stats.acceptanceRate >= 50
        ? 'text-yellow-600'
        : 'text-red-600';

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard
          title="Vorgeschlagen"
          value={stats.totalSuggested}
          icon={<Sparkles className="h-5 w-5 text-blue-500" />}
        />
        <SummaryCard
          title="Akzeptiert"
          value={stats.totalAccepted}
          subtitle={`${formatPercent(stats.acceptanceRate)} Rate`}
          icon={<Check className="h-5 w-5 text-green-500" />}
          variant="success"
        />
        <SummaryCard
          title="Abgelehnt"
          value={stats.totalRejected}
          icon={<X className="h-5 w-5 text-red-500" />}
        />
        <SummaryCard
          title="Verschoben"
          value={stats.totalSnoozed}
          icon={<Clock className="h-5 w-5 text-orange-500" />}
        />
      </div>

      {/* Savings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Einsparungen</CardTitle>
          <CardDescription>
            Zeitraum: {formatDate(stats.periodStart)} -{' '}
            {formatDate(stats.periodEnd)}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <div className="text-sm text-muted-foreground">
                Geschaetzte Einsparungen
              </div>
              <div className="text-2xl font-bold">
                {formatCurrency(stats.estimatedSavings)}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">
                Realisierte Einsparungen
              </div>
              <div className="text-2xl font-bold text-green-600">
                {formatCurrency(stats.realizedSavings)}
              </div>
            </div>
          </div>
          <div className="mt-4">
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Realisierungsrate</span>
              <span>
                {stats.estimatedSavings > 0
                  ? formatPercent(
                      (stats.realizedSavings / stats.estimatedSavings) * 100
                    )
                  : '-'}
              </span>
            </div>
            <Progress
              value={
                stats.estimatedSavings > 0
                  ? (stats.realizedSavings / stats.estimatedSavings) * 100
                  : 0
              }
            />
          </div>
        </CardContent>
      </Card>

      {/* By Priority */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Nach Prioritaet</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Object.entries(stats.byPriority).map(([priority, count]) => {
              const config = PRIORITY_CONFIG[priority as ActionPriority];
              if (!config) return null;
              const Icon = config.icon;
              return (
                <div
                  key={priority}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-2">
                    <Icon className={`h-4 w-4 ${config.textColor}`} />
                    <span>{config.label}</span>
                  </div>
                  <Badge variant="secondary">{count}</Badge>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ==================== Main Panel Component ====================

export interface PredictiveActionPanelProps {
  /** Zeige nur kritische Aktionen (Dashboard-Modus) */
  criticalOnly?: boolean;
  /** Maximale Anzahl Aktionen */
  limit?: number;
  /** Kompakte Darstellung */
  compact?: boolean;
}

export function PredictiveActionPanel({
  criticalOnly = false,
  limit = 10,
  compact = false,
}: PredictiveActionPanelProps) {
  const [activeTab, setActiveTab] = useState('critical');
  const [loadingActionId, setLoadingActionId] = useState<string | null>(null);

  // Data fetching
  const {
    data: criticalData,
    isLoading: criticalLoading,
    error: criticalError,
    refetch: refetchCritical,
  } = useCriticalActions(limit);

  const {
    data: skontoData,
    isLoading: skontoLoading,
  } = useSkontoActions(limit);

  const {
    data: dunningData,
    isLoading: dunningLoading,
  } = useDunningActions(limit);

  const {
    data: stats,
    isLoading: statsLoading,
  } = useActionStatistics(30);

  // Mutations
  const acceptMutation = useAcceptAction();
  const rejectMutation = useRejectAction();
  const snoozeMutation = useSnoozeAction();

  // Handlers
  const handleAccept = async (
    actionId: string,
    executeImmediately?: boolean
  ) => {
    setLoadingActionId(actionId);
    try {
      await acceptMutation.mutateAsync({
        actionId,
        request: { executeImmediately },
      });
    } finally {
      setLoadingActionId(null);
    }
  };

  const handleReject = async (actionId: string, reason?: string) => {
    setLoadingActionId(actionId);
    try {
      await rejectMutation.mutateAsync({
        actionId,
        request: { reason },
      });
    } finally {
      setLoadingActionId(null);
    }
  };

  const handleSnooze = async (actionId: string, hours?: number) => {
    setLoadingActionId(actionId);
    try {
      await snoozeMutation.mutateAsync({
        actionId,
        request: { snoozeHours: hours },
      });
    } finally {
      setLoadingActionId(null);
    }
  };

  // Loading state
  if (criticalLoading && !criticalData) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (criticalError) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
          <p className="text-lg font-medium mb-2">
            Fehler beim Laden der Aktionen
          </p>
          <p className="text-muted-foreground mb-4">
            Die Handlungsvorschlaege konnten nicht geladen werden.
          </p>
          <Button variant="outline" onClick={() => refetchCritical()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    );
  }

  // Summary calculations
  const summary = criticalData?.summary ?? {};
  const criticalCount = summary.critical ?? 0;
  const totalPotentialSavings = summary.totalPotentialSavings ?? 0;

  // Compact/Dashboard mode
  if (compact || criticalOnly) {
    const actions = criticalData?.actions ?? [];

    return (
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-purple-500" />
                Handlungsvorschlaege
              </CardTitle>
              <CardDescription>
                {criticalCount > 0
                  ? `${criticalCount} kritische Aktionen`
                  : 'Keine dringenden Aktionen'}
              </CardDescription>
            </div>
            {totalPotentialSavings > 0 && (
              <Badge variant="secondary" className="text-green-600">
                <TrendingUp className="h-3 w-3 mr-1" />
                {formatCurrency(totalPotentialSavings)} Einsparpotenzial
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <ActionsList
            actions={actions.slice(0, 5)}
            onAccept={handleAccept}
            onReject={handleReject}
            onSnooze={handleSnooze}
            loadingActionId={loadingActionId}
          />
          {actions.length > 5 && (
            <Button
              variant="ghost"
              className="w-full mt-3"
              onClick={() => {
                /* Navigation to full view */
              }}
            >
              Alle {actions.length} Aktionen anzeigen
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          )}
        </CardContent>
      </Card>
    );
  }

  // Full panel mode with tabs
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-purple-500" />
            Proaktive Handlungsvorschlaege
          </h2>
          <p className="text-muted-foreground">
            KI-generierte Empfehlungen basierend auf Ihren Daten
          </p>
        </div>
        {totalPotentialSavings > 0 && (
          <Card className="border-green-200 dark:border-green-800">
            <CardContent className="py-3 px-4">
              <div className="text-xs text-muted-foreground">
                Einsparpotenzial
              </div>
              <div className="text-xl font-bold text-green-600">
                {formatCurrency(totalPotentialSavings)}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard
          title="Kritisch"
          value={summary.critical ?? 0}
          icon={<AlertTriangle className="h-5 w-5 text-red-500" />}
          variant={criticalCount > 0 ? 'warning' : 'default'}
        />
        <SummaryCard
          title="Skonto laeuft ab"
          value={summary.expiringThisWeek ?? 0}
          subtitle="Diese Woche"
          icon={<Percent className="h-5 w-5 text-orange-500" />}
        />
        <SummaryCard
          title="Mahnungen"
          value={summary.totalOutstanding ?? 0}
          subtitle="Offene Rechnungen"
          icon={<Receipt className="h-5 w-5 text-blue-500" />}
        />
        <SummaryCard
          title="Anrufe noetig"
          value={summary.needsCall ?? 0}
          icon={<Phone className="h-5 w-5 text-purple-500" />}
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="critical" className="gap-1">
            <AlertTriangle className="h-4 w-4" />
            Kritisch
            {criticalCount > 0 && (
              <Badge variant="destructive" className="ml-1">
                {criticalCount}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="skonto" className="gap-1">
            <Percent className="h-4 w-4" />
            Skonto
          </TabsTrigger>
          <TabsTrigger value="dunning" className="gap-1">
            <Receipt className="h-4 w-4" />
            Mahnungen
          </TabsTrigger>
          <TabsTrigger value="stats" className="gap-1">
            <TrendingUp className="h-4 w-4" />
            Statistiken
          </TabsTrigger>
        </TabsList>

        {/* Critical Tab */}
        <TabsContent value="critical" className="mt-4">
          {criticalLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-32" />
              ))}
            </div>
          ) : (
            <ActionsList
              actions={criticalData?.actions ?? []}
              onAccept={handleAccept}
              onReject={handleReject}
              onSnooze={handleSnooze}
              loadingActionId={loadingActionId}
            />
          )}
        </TabsContent>

        {/* Skonto Tab */}
        <TabsContent value="skonto" className="mt-4">
          {skontoLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-32" />
              ))}
            </div>
          ) : (
            <ActionsList
              actions={skontoData?.actions ?? []}
              onAccept={handleAccept}
              onReject={handleReject}
              onSnooze={handleSnooze}
              loadingActionId={loadingActionId}
            />
          )}
        </TabsContent>

        {/* Dunning Tab */}
        <TabsContent value="dunning" className="mt-4">
          {dunningLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-32" />
              ))}
            </div>
          ) : (
            <ActionsList
              actions={dunningData?.actions ?? []}
              onAccept={handleAccept}
              onReject={handleReject}
              onSnooze={handleSnooze}
              loadingActionId={loadingActionId}
            />
          )}
        </TabsContent>

        {/* Statistics Tab */}
        <TabsContent value="stats" className="mt-4">
          {statsLoading ? (
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-4">
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} className="h-24" />
                ))}
              </div>
              <Skeleton className="h-48" />
            </div>
          ) : stats ? (
            <StatisticsPanel stats={stats} />
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Keine Statistiken verfuegbar
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
