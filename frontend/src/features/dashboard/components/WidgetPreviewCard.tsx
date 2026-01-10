/**
 * WidgetPreviewCard - Vorschaukarte fuer Widget-Katalog
 *
 * Zeigt eine Vorschau des Widgets mit Icon, Name und Beschreibung.
 * Ermoeglicht das Hinzufuegen zum Dashboard per Button.
 */

import { Plus, Check } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { WidgetDefinition } from '../registry';
import { cn } from '@/lib/utils';

interface WidgetPreviewCardProps {
  type: string;
  definition: WidgetDefinition;
  isAdded: boolean;
  onAdd: (type: string) => void;
}

const CATEGORY_LABELS: Record<string, { label: string; className: string }> = {
  info: { label: 'Information', className: 'bg-blue-500/10 text-blue-600 border-blue-500/20' },
  action: { label: 'Aktion', className: 'bg-green-500/10 text-green-600 border-green-500/20' },
  data: { label: 'Daten', className: 'bg-purple-500/10 text-purple-600 border-purple-500/20' },
};

export function WidgetPreviewCard({
  type,
  definition,
  isAdded,
  onAdd,
}: WidgetPreviewCardProps) {
  const Icon = definition.icon;
  const categoryInfo = CATEGORY_LABELS[definition.category] || CATEGORY_LABELS.info;

  return (
    <Card
      className={cn(
        'group transition-all duration-200 hover:shadow-md',
        isAdded && 'border-primary/50 bg-primary/5'
      )}
    >
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div
            className={cn(
              'p-2 rounded-lg shrink-0',
              isAdded ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
            )}
          >
            <Icon className="h-5 w-5" />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-medium text-sm truncate">{definition.label}</h4>
              <Badge
                variant="outline"
                className={cn('text-[10px] px-1.5 py-0', categoryInfo.className)}
              >
                {categoryInfo.label}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground line-clamp-2">
              {definition.description}
            </p>
          </div>

          {/* Add Button */}
          <Button
            variant={isAdded ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => !isAdded && onAdd(type)}
            disabled={isAdded}
            className="shrink-0"
          >
            {isAdded ? (
              <>
                <Check className="h-4 w-4 mr-1" />
                Aktiv
              </>
            ) : (
              <>
                <Plus className="h-4 w-4 mr-1" />
                Hinzufügen
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default WidgetPreviewCard;
