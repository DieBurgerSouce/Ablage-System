/**
 * TagBadge - Tag-Darstellung mit Farbe
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { KnowledgeTag } from '../types/knowledge-types';

interface TagBadgeProps {
  tag: KnowledgeTag | string;
  onClick?: () => void;
  onRemove?: () => void;
  className?: string;
}

export function TagBadge({ tag, onClick, onRemove, className }: TagBadgeProps) {
  const isTagObject = typeof tag === 'object';
  const name = isTagObject ? tag.name : tag;
  const color = isTagObject && tag.color ? tag.color : undefined;

  // Generiere Stil basierend auf Farbe
  const style = color
    ? {
        backgroundColor: `${color}20`,
        borderColor: color,
        color: color,
      }
    : undefined;

  return (
    <Badge
      variant={color ? 'outline' : 'secondary'}
      style={style}
      className={cn('cursor-pointer', className)}
      onClick={onClick}
    >
      {name}
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="ml-1 hover:opacity-70"
        >
          &times;
        </button>
      )}
    </Badge>
  );
}
