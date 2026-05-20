/**
 * Bottleneck List Component
 *
 * Zeigt erkannte Prozess-Engpässe mit Details und Empfehlungen.
 */

import {
  AlertTriangle,
  Clock,
  Users,
  XCircle,
  Activity,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { useBottlenecks, type Bottleneck, type BottleneckType, type BottleneckSeverity } from '../hooks/useProcessMining';

const BOTTLENECK_TYPE_CONFIG: Record<
  BottleneckType,
  { label: string; icon: typeof Clock; description: string }
> = {
  duration: {
    label: 'Lange Dauer',
    icon: Clock,
    description: 'Dieser Schritt dauert länger als erwartet',
  },
  queue: {
    label: 'Warteschlange',
    icon: Users,
    description: 'Dokumente stauen sich vor diesem Schritt',
  },
  failure: {
    label: 'Fehler',
    icon: XCircle,
    description: 'Hohe Fehlerrate bei diesem Schritt',
  },
  resource: {
    label: 'Ressourcen',
    icon: Users,
    description: 'Zu viele manuelle Eingriffe erforderlich',
  },
};

const SEVERITY_CONFIG: Record<
  BottleneckSeverity,
  { label: string; color: string; bgColor: string }
> = {
  critical: {
    label: 'Kritisch',
    color: 'text-red-600',
    bgColor: 'bg-red-100',
  },
  high: {
    label: 'Hoch',
    color: 'text-orange-600',
    bgColor: 'bg-orange-100',
  },
  medium: {
    label: 'Mittel',
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-100',
  },
  low: {
    label: 'Niedrig',
    color: 'text-green-600',
    bgColor: 'bg-green-100',
  },
};

function BottleneckCard({ bottleneck }: { bottleneck: Bottleneck }) {
  const typeConfig = BOTTLENECK_TYPE_CONFIG[bottleneck.type] || {
    label: bottleneck.type,
    icon: Activity,
    description: '',
  };
  const severityConfig = SEVERITY_CONFIG[bottleneck.severity] || SEVERITY_CONFIG.low;
  const TypeIcon = typeConfig.icon;

  return (
    <AccordionItem value={`${bottleneck.type}-${bottleneck.location}`}>
      <AccordionTrigger className="hover:no-underline">
        <div className="flex items-center gap-4 w-full">
          <div className={`p-2 rounded-lg ${severityConfig.bgColor}`}>
            <TypeIcon className={`h-4 w-4 ${severityConfig.color}`} />
          </div>
          <div className="flex-1 text-left">
            <div className="font-medium">{bottleneck.location}</div>
            <div className="text-sm text-muted-foreground">{typeConfig.label}</div>
          </div>
          <Badge className={`${severityConfig.bgColor} ${severityConfig.color} border-0`}>
            {severityConfig.label}
          </Badge>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Score:</span>
            <Progress
              value={bottleneck.score * 100}
              className="w-16 h-2"
            />
            <span className="font-medium text-sm">
              {(bottleneck.score * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="pl-12 space-y-4">
          <p className="text-sm text-muted-foreground">{typeConfig.description}</p>

          {/* Details */}
          {bottleneck.details && Object.keys(bottleneck.details).length > 0 && (
            <div className="grid grid-cols-2 gap-4 p-4 bg-muted/50 rounded-lg">
              {Object.entries(bottleneck.details).map(([key, value]) => (
                <div key={key}>
                  <div className="text-xs text-muted-foreground">
                    {key.replace(/_/g, ' ')}
                  </div>
                  <div className="font-medium">
                    {typeof value === 'number'
                      ? key.includes('duration') || key.includes('ms')
                        ? `${(Number(value) / 1000).toFixed(1)}s`
                        : key.includes('rate')
                        ? `${(Number(value) * 100).toFixed(1)}%`
                        : value.toLocaleString('de-DE')
                      : String(value)}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Recommendation */}
          {bottleneck.recommendation && (
            <div className="flex items-start gap-2 p-4 bg-blue-50 text-blue-800 rounded-lg">
              <ChevronRight className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <div>
                <div className="font-medium text-sm">Empfehlung</div>
                <p className="text-sm">{bottleneck.recommendation}</p>
              </div>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

export function BottleneckList() {
  const { data, isLoading, error } = useBottlenecks(30);

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
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Erkannte Engpässe</CardTitle>
          <CardDescription>Fehler beim Laden der Daten</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            Keine Daten verfügbar
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Erkannte Engpässe
            </CardTitle>
            <CardDescription>
              {data.bottleneck_count} Engpässe in den letzten {data.period_days} Tagen
            </CardDescription>
          </div>
          <div className="text-right">
            <div className="text-sm text-muted-foreground">Gesamt-Score</div>
            <div className="flex items-center gap-2">
              <Progress
                value={data.overall_score * 100}
                className="w-24 h-2"
              />
              <Badge
                className={`${SEVERITY_CONFIG[data.overall_severity]?.bgColor || ''} ${
                  SEVERITY_CONFIG[data.overall_severity]?.color || ''
                } border-0`}
              >
                {(data.overall_score * 100).toFixed(0)}%
              </Badge>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {data.bottlenecks.length > 0 ? (
          <Accordion type="single" collapsible className="w-full">
            {data.bottlenecks.map((bottleneck, index) => (
              <BottleneckCard key={index} bottleneck={bottleneck} />
            ))}
          </Accordion>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Activity className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Keine Engpässe erkannt</p>
            <p className="text-sm mt-1">
              Ihr Prozess läuft optimal!
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
