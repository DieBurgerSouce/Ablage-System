/**
 * Automation Suggestions Component
 *
 * Zeigt Automatisierungsvorschläge mit Ein-Klick-Aktivierung.
 */

import { useState } from 'react';
import { Zap, Play, X, RefreshCw, TrendingUp, Clock, CheckCircle, Loader2, Lightbulb } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import {
  useAutomationSuggestions,
  useSuggestionStats,
  useActivateSuggestion,
  useRejectSuggestion,
  useGenerateSuggestions,
  type AutomationSuggestion,
  type SuggestionType,
} from '../hooks/useProcessMining';

const SUGGESTION_TYPE_LABELS: Record<SuggestionType, { label: string; icon: typeof Zap }> = {
  auto_classification: { label: 'Auto-Klassifikation', icon: Zap },
  auto_routing: { label: 'Auto-Routing', icon: TrendingUp },
  auto_approval: { label: 'Auto-Freigabe', icon: CheckCircle },
  auto_entity_link: { label: 'Entity-Erkennung', icon: Lightbulb },
  workflow_optimization: { label: 'Workflow-Optimierung', icon: RefreshCw },
};

function SuggestionCard({
  suggestion,
  onActivate,
  onReject,
  isActivating,
  isRejecting,
}: {
  suggestion: AutomationSuggestion;
  onActivate: () => void;
  onReject: () => void;
  isActivating: boolean;
  isRejecting: boolean;
}) {
  const config = SUGGESTION_TYPE_LABELS[suggestion.suggestion_type] || {
    label: suggestion.suggestion_type,
    icon: Zap,
  };
  const TypeIcon = config.icon;

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <TypeIcon className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h4 className="font-medium">{suggestion.title}</h4>
            <Badge variant="outline" className="mt-1">
              {config.label}
            </Badge>
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-green-600">
            ~{suggestion.potential_savings_hours?.toFixed(0) || 0}h
          </div>
          <div className="text-xs text-muted-foreground">pro Jahr</div>
        </div>
      </div>

      {suggestion.description && (
        <p className="text-sm text-muted-foreground">{suggestion.description}</p>
      )}

      <div className="flex items-center gap-4 text-sm">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-1">
                <span className="text-muted-foreground">Konfidenz:</span>
                <Progress
                  value={suggestion.confidence * 100}
                  className="w-16 h-2"
                />
                <span className="font-medium">
                  {(suggestion.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p>Wie sicher sind wir, dass diese Automatisierung funktioniert</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {suggestion.frequency_per_week && (
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">
              {suggestion.frequency_per_week}x/Woche
            </span>
          </div>
        )}
      </div>

      <div className="flex gap-2 pt-2">
        <Button
          size="sm"
          onClick={onActivate}
          disabled={isActivating || isRejecting}
          className="flex-1"
        >
          {isActivating ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Play className="h-4 w-4 mr-2" />
          )}
          Aktivieren
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onReject}
          disabled={isActivating || isRejecting}
        >
          {isRejecting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <X className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}

export function AutomationSuggestions() {
  const { data, isLoading, refetch } = useAutomationSuggestions('pending', 10);
  const { data: stats } = useSuggestionStats();
  const generateMutation = useGenerateSuggestions();
  const activateMutation = useActivateSuggestion();
  const rejectMutation = useRejectSuggestion();

  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);

  const handleGenerate = async () => {
    try {
      await generateMutation.mutateAsync({ days: 30, save: true });
      toast.success('Neue Vorschläge wurden generiert');
    } catch {
      toast.error('Fehler beim Generieren der Vorschläge');
    }
  };

  const handleActivate = async (suggestionId: string) => {
    setActivatingId(suggestionId);
    try {
      await activateMutation.mutateAsync({ suggestionId });
      toast.success('Automatisierung wurde aktiviert');
    } catch {
      toast.error('Fehler beim Aktivieren');
    } finally {
      setActivatingId(null);
    }
  };

  const handleReject = async (suggestionId: string) => {
    setRejectingId(suggestionId);
    try {
      await rejectMutation.mutateAsync({ suggestionId });
      toast.success('Vorschlag wurde abgelehnt');
    } catch {
      toast.error('Fehler beim Ablehnen');
    } finally {
      setRejectingId(null);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64 mt-1" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const suggestions = data?.items || [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Automatisierungsvorschläge
          </CardTitle>
          <CardDescription>
            Erkannte Optimierungspotenziale basierend auf Ihren Prozessen
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Aktualisieren
          </Button>
          <Button
            size="sm"
            onClick={handleGenerate}
            disabled={generateMutation.isPending}
          >
            {generateMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Lightbulb className="h-4 w-4 mr-2" />
            )}
            Neue generieren
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Stats Summary */}
        {stats && (
          <div className="grid grid-cols-3 gap-4 mb-6 p-4 bg-muted/50 rounded-lg">
            <div className="text-center">
              <div className="text-2xl font-bold">{stats.total_pending}</div>
              <div className="text-xs text-muted-foreground">Offen</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {stats.total_activated}
              </div>
              <div className="text-xs text-muted-foreground">Aktiviert</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {stats.realized_savings_hours.toFixed(0)}h
              </div>
              <div className="text-xs text-muted-foreground">Gespart/Jahr</div>
            </div>
          </div>
        )}

        {/* Suggestions List */}
        {suggestions.length > 0 ? (
          <div className="space-y-4">
            {suggestions.map((suggestion) => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                onActivate={() => handleActivate(suggestion.id)}
                onReject={() => handleReject(suggestion.id)}
                isActivating={activatingId === suggestion.id}
                isRejecting={rejectingId === suggestion.id}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Zap className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Keine offenen Vorschläge</p>
            <p className="text-sm mt-1">
              Klicken Sie auf &quot;Neue generieren&quot; um Optimierungspotenziale zu finden
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
