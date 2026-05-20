import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  CheckCircle,
  ThumbsUp,
  ThumbsDown,
  AlertTriangle,
  Eye,
  DollarSign,
  Clock,
  X,
  FileText,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { Link } from '@tanstack/react-router';
import type { SmartInboxItemResponse, InboxActionType } from '../types/smart-inbox-types';

interface InboxItemCardProps {
  item: SmartInboxItemResponse;
  onAction: (itemId: string, action: InboxActionType) => void;
  onSnooze: (itemId: string, snoozeUntil: string) => void;
  onDismiss: (itemId: string) => void;
  isActioning?: boolean;
}

const ACTION_CONFIG: Record<string, { label: string; icon: typeof CheckCircle; variant: 'default' | 'outline' | 'destructive' }> = {
  complete: { label: 'Abschließen', icon: CheckCircle, variant: 'default' },
  approve: { label: 'Genehmigen', icon: ThumbsUp, variant: 'default' },
  reject: { label: 'Ablehnen', icon: ThumbsDown, variant: 'destructive' },
  escalate: { label: 'Eskalieren', icon: AlertTriangle, variant: 'outline' },
  review: { label: 'Prüfen', icon: Eye, variant: 'outline' },
  pay: { label: 'Bezahlen', icon: DollarSign, variant: 'default' },
};

function getPriorityColor(mlPriority: number): string {
  if (mlPriority > 0.7) return 'border-l-red-500';
  if (mlPriority > 0.4) return 'border-l-yellow-500';
  return 'border-l-green-500';
}

function getPriorityLabel(mlPriority: number): string {
  if (mlPriority > 0.7) return 'Hoch';
  if (mlPriority > 0.4) return 'Mittel';
  return 'Niedrig';
}

function isDeadlineSoon(deadline: string | null): boolean {
  if (!deadline) return false;
  const deadlineDate = new Date(deadline);
  const now = new Date();
  const diffHours = (deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60);
  return diffHours < 24 && diffHours > 0;
}

export function InboxItemCard({
  item,
  onAction,
  onSnooze,
  onDismiss,
  isActioning = false,
}: InboxItemCardProps) {
  const priorityColor = getPriorityColor(item.mlPriority);
  const priorityLabel = getPriorityLabel(item.mlPriority);
  const deadlineSoon = isDeadlineSoon(item.deadline);

  const handleSnooze = (hours: number) => {
    const snoozeUntil = new Date();
    snoozeUntil.setHours(snoozeUntil.getHours() + hours);
    onSnooze(item.id, snoozeUntil.toISOString());
  };

  const handleSnoozeTomorrow = () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(9, 0, 0, 0);
    onSnooze(item.id, tomorrow.toISOString());
  };

  const handleSnoozeNextWeek = () => {
    const nextWeek = new Date();
    nextWeek.setDate(nextWeek.getDate() + 7);
    nextWeek.setHours(9, 0, 0, 0);
    onSnooze(item.id, nextWeek.toISOString());
  };

  return (
    <Card className={`border-l-4 ${priorityColor}`}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="font-semibold truncate">{item.title}</h3>
              {item.documentId && (
                <Link
                  to="/documents/$documentId"
                  params={{ documentId: item.documentId }}
                  className="flex-shrink-0"
                >
                  <Button variant="ghost" size="icon" className="h-6 w-6">
                    <FileText className="h-4 w-4" />
                  </Button>
                </Link>
              )}
            </div>
            {item.description && (
              <p className="text-sm text-muted-foreground line-clamp-2">
                {item.description}
              </p>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onDismiss(item.id)}
            disabled={isActioning}
            className="flex-shrink-0"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{item.sourceType}</Badge>
          {item.category && <Badge variant="secondary">{item.category}</Badge>}
          <Badge variant={item.mlPriority > 0.7 ? 'destructive' : 'default'}>
            Priorität: {priorityLabel}
          </Badge>
          {item.deadline && (
            <Badge variant={deadlineSoon ? 'destructive' : 'outline'}>
              <Clock className="h-3 w-3 mr-1" />
              {formatDistanceToNow(new Date(item.deadline), {
                addSuffix: true,
                locale: de,
              })}
            </Badge>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {item.recommendedActions.map((recAction) => {
            const config = ACTION_CONFIG[recAction.action];
            if (!config) return null;

            const Icon = config.icon;
            return (
              <Button
                key={recAction.action}
                variant={config.variant}
                size="sm"
                onClick={() => onAction(item.id, recAction.action as InboxActionType)}
                disabled={isActioning}
                className="flex items-center gap-2"
                title={recAction.description}
              >
                <Icon className="h-4 w-4" />
                {recAction.label || config.label}
              </Button>
            );
          })}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" disabled={isActioning}>
                <Clock className="h-4 w-4 mr-2" />
                Später
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onClick={() => handleSnooze(1)}>
                In 1 Stunde
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleSnooze(3)}>
                In 3 Stunden
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleSnoozeTomorrow}>
                Morgen
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleSnoozeNextWeek}>
                Nächste Woche
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </CardContent>
    </Card>
  );
}
