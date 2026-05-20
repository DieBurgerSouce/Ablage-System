// Hint Card - Single hint display with action buttons

import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CheckCircle2, XCircle, Clock, ExternalLink } from 'lucide-react';
import {
  CATEGORY_CONFIG,
  PRIORITY_CONFIG,
  STATUS_CONFIG,
  UI_LABELS,
  type Hint,
} from '../types/proactive-assistant-types';
import { useUpdateHintStatusMutation } from '../hooks/use-proactive-assistant-queries';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';

interface HintCardProps {
  hint: Hint;
  compact?: boolean;
}

export function HintCard({ hint, compact = false }: HintCardProps) {
  const updateStatusMutation = useUpdateHintStatusMutation();

  const categoryConfig = CATEGORY_CONFIG[hint.category];
  const priorityConfig = PRIORITY_CONFIG[hint.priority];
  const statusConfig = STATUS_CONFIG[hint.status];

  const handleAccept = () => {
    updateStatusMutation.mutate({
      hintId: hint.hintId,
      status: 'confirmed',
    });
  };

  const handleDismiss = () => {
    updateStatusMutation.mutate({
      hintId: hint.hintId,
      status: 'dismissed',
    });
  };

  const handleDefer = () => {
    updateStatusMutation.mutate({
      hintId: hint.hintId,
      status: 'seen',
    });
  };

  const handleMarkActed = () => {
    updateStatusMutation.mutate({
      hintId: hint.hintId,
      status: 'acted',
    });
  };

  const timeAgo = formatDistanceToNow(hint.createdAt, {
    addSuffix: true,
    locale: de,
  });

  return (
    <Card
      className={`transition-all hover:shadow-md ${
        hint.priority === 'critical' ? 'border-red-400' : ''
      }`}
    >
      <CardHeader className={compact ? 'pb-2' : ''}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg">{categoryConfig.icon}</span>
              <Badge
                variant={priorityConfig.variant}
                className={priorityConfig.bgColor}
              >
                {priorityConfig.label}
              </Badge>
              <Badge variant={statusConfig.variant} className={statusConfig.bgColor}>
                {statusConfig.label}
              </Badge>
            </div>
            <h3 className={`font-semibold ${compact ? 'text-sm' : 'text-base'}`}>
              {hint.title}
            </h3>
          </div>
          {hint.actionUrl && (
            <Button variant="ghost" size="sm" asChild>
              <a
                href={hint.actionUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className={compact ? 'py-2' : ''}>
        <p className={`text-muted-foreground ${compact ? 'text-xs' : 'text-sm'}`}>
          {hint.description}
        </p>

        {hint.recommendedAction && !compact && (
          <div className="mt-3 p-3 bg-blue-50 rounded-md border border-blue-200">
            <p className="text-sm text-blue-900">
              <strong>Empfohlene Aktion:</strong> {hint.recommendedAction}
            </p>
          </div>
        )}

        {!compact && (
          <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
            <span className={categoryConfig.color}>
              {categoryConfig.label}
            </span>
            <span>•</span>
            <span>{timeAgo}</span>
          </div>
        )}
      </CardContent>

      {hint.status !== 'acted' && hint.status !== 'dismissed' && (
        <CardFooter className={`gap-2 ${compact ? 'pt-2' : ''}`}>
          {hint.status === 'new' && (
            <>
              <Button
                size={compact ? 'sm' : 'default'}
                variant="default"
                onClick={handleAccept}
                disabled={updateStatusMutation.isPending}
              >
                <CheckCircle2 className="h-4 w-4 mr-1" />
                {UI_LABELS.actions.accept}
              </Button>
              <Button
                size={compact ? 'sm' : 'default'}
                variant="outline"
                onClick={handleDefer}
                disabled={updateStatusMutation.isPending}
              >
                <Clock className="h-4 w-4 mr-1" />
                {UI_LABELS.actions.defer}
              </Button>
              <Button
                size={compact ? 'sm' : 'default'}
                variant="ghost"
                onClick={handleDismiss}
                disabled={updateStatusMutation.isPending}
              >
                <XCircle className="h-4 w-4 mr-1" />
                {UI_LABELS.actions.dismiss}
              </Button>
            </>
          )}
          {(hint.status === 'seen' || hint.status === 'confirmed') && (
            <>
              <Button
                size={compact ? 'sm' : 'default'}
                variant="default"
                onClick={handleMarkActed}
                disabled={updateStatusMutation.isPending}
              >
                <CheckCircle2 className="h-4 w-4 mr-1" />
                {UI_LABELS.actions.markAsActed}
              </Button>
              <Button
                size={compact ? 'sm' : 'default'}
                variant="ghost"
                onClick={handleDismiss}
                disabled={updateStatusMutation.isPending}
              >
                <XCircle className="h-4 w-4 mr-1" />
                {UI_LABELS.actions.dismiss}
              </Button>
            </>
          )}
        </CardFooter>
      )}
    </Card>
  );
}
