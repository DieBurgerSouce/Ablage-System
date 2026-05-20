/**
 * LifeEventCard - Karte für einen Lebensereignis-Typ
 *
 * Zeigt Icon, deutschen Titel und Beschreibung.
 * Falls aktives Ereignis existiert, wird Fortschritt angezeigt.
 */

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
  Truck,
  Heart,
  Baby,
  Briefcase,
  Armchair,
  Cross,
  Home,
  Split,
  type LucideIcon,
} from 'lucide-react';
import type { LifeEventType } from '../api/life-events-api';

// =============================================================================
// Event Type Configuration
// =============================================================================

interface EventTypeConfig {
  icon: LucideIcon;
  label: string;
  description: string;
  color: string;
}

// eslint-disable-next-line react-refresh/only-export-components
export const EVENT_TYPE_CONFIG: Record<LifeEventType, EventTypeConfig> = {
  umzug: {
    icon: Truck,
    label: 'Umzug',
    description: 'Adressänderung, Ummeldungen und Verträge',
    color: 'text-blue-600 bg-blue-50 dark:bg-blue-950',
  },
  heirat: {
    icon: Heart,
    label: 'Heirat',
    description: 'Standesamt, Steuerklasse und Versicherungen',
    color: 'text-pink-600 bg-pink-50 dark:bg-pink-950',
  },
  kind: {
    icon: Baby,
    label: 'Geburt',
    description: 'Elterngeld, Kindergeld und Anmeldungen',
    color: 'text-green-600 bg-green-50 dark:bg-green-950',
  },
  jobwechsel: {
    icon: Briefcase,
    label: 'Jobwechsel',
    description: 'Kündigung, Versicherungen und Steuern',
    color: 'text-orange-600 bg-orange-50 dark:bg-orange-950',
  },
  ruhestand: {
    icon: Armchair,
    label: 'Ruhestand',
    description: 'Rentenantrag, Versorgung und Vorsorge',
    color: 'text-purple-600 bg-purple-50 dark:bg-purple-950',
  },
  todesfall: {
    icon: Cross,
    label: 'Todesfall',
    description: 'Behördengaenge, Erbschaft und Nachlass',
    color: 'text-gray-600 bg-gray-50 dark:bg-gray-950',
  },
  immobilienkauf: {
    icon: Home,
    label: 'Immobilienkauf',
    description: 'Notar, Finanzierung und Grundsteuer',
    color: 'text-teal-600 bg-teal-50 dark:bg-teal-950',
  },
  scheidung: {
    icon: Split,
    label: 'Scheidung',
    description: 'Anwalt, Trennungsjahr und Versorgungsausgleich',
    color: 'text-red-600 bg-red-50 dark:bg-red-950',
  },
};

// =============================================================================
// Status Labels
// =============================================================================

const STATUS_LABELS: Record<string, string> = {
  pending: 'Ausstehend',
  confirmed: 'Bestätigt',
  in_progress: 'In Bearbeitung',
  completed: 'Abgeschlossen',
};

// =============================================================================
// Component
// =============================================================================

interface LifeEventCardProps {
  eventType: LifeEventType;
  activeEvent?: LifeEvent;
  onStart: (eventType: LifeEventType) => void;
  onOpen: (eventId: string) => void;
}

export function LifeEventCard({ eventType, activeEvent, onStart, onOpen }: LifeEventCardProps) {
  const config = EVENT_TYPE_CONFIG[eventType];
  const Icon = config.icon;

  const completedItems = activeEvent?.checklist.filter((item) => item.done).length ?? 0;
  const totalItems = activeEvent?.checklist.length ?? 0;
  const progressPercent = totalItems > 0 ? Math.round((completedItems / totalItems) * 100) : 0;

  return (
    <Card className="group hover:shadow-md transition-shadow">
      <CardContent className="p-5">
        <div className="flex items-start gap-4">
          <div className={`rounded-lg p-3 ${config.color}`}>
            <Icon className="w-6 h-6" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-base">{config.label}</h3>
            <p className="text-sm text-muted-foreground mt-0.5">{config.description}</p>

            {activeEvent ? (
              <div className="mt-3 space-y-2">
                <div className="flex items-center justify-between">
                  <Badge variant="secondary" className="text-xs">
                    {STATUS_LABELS[activeEvent.status] ?? activeEvent.status}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {completedItems}/{totalItems} erledigt
                  </span>
                </div>
                <Progress value={progressPercent} className="h-2" />
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full mt-1"
                  onClick={() => onOpen(activeEvent.id)}
                >
                  Fortsetzen
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => onStart(eventType)}
              >
                Starten
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
