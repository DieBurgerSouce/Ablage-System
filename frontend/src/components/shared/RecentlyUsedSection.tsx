import { AnimatedList, AnimatedListItem } from '@/components/animations';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

interface RecentlyUsedItem {
  id: string;
  label: string;
  sublabel?: string;
  icon?: ReactNode;
}

interface RecentlyUsedSectionProps {
  /** Items to display */
  items: RecentlyUsedItem[];
  /** Called when an item is clicked */
  onItemClick: (item: RecentlyUsedItem) => void;
  /** Called when clear all is triggered */
  onClear: () => void;
  /** Section title (default: "Zuletzt verwendet") */
  title?: string;
  /** Max items to show (default: 5) */
  maxDisplay?: number;
  /** Layout mode */
  layout?: 'chips' | 'list';
  /** Additional CSS classes */
  className?: string;
}

export function RecentlyUsedSection({
  items,
  onItemClick,
  onClear,
  title = 'Zuletzt verwendet',
  maxDisplay = 5,
  layout = 'chips',
  className,
}: RecentlyUsedSectionProps) {
  if (items.length === 0) return null;

  const displayed = items.slice(0, maxDisplay);

  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{title}</span>
        <Button variant="ghost" size="sm" className="h-auto px-1 py-0 text-xs text-muted-foreground" onClick={onClear}>
          Alle löschen
        </Button>
      </div>

      {layout === 'chips' ? (
        <AnimatedList className="flex gap-2 overflow-x-auto pb-1">
          {displayed.map((item) => (
            <AnimatedListItem key={item.id}>
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 gap-1.5 text-xs"
                onClick={() => onItemClick(item)}
              >
                {item.icon}
                {item.label}
              </Button>
            </AnimatedListItem>
          ))}
        </AnimatedList>
      ) : (
        <AnimatedList className="space-y-0.5">
          {displayed.map((item) => (
            <AnimatedListItem key={item.id}>
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                onClick={() => onItemClick(item)}
              >
                {item.icon && <span className="shrink-0 text-muted-foreground">{item.icon}</span>}
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{item.label}</div>
                  {item.sublabel && (
                    <div className="truncate text-xs text-muted-foreground">{item.sublabel}</div>
                  )}
                </div>
              </button>
            </AnimatedListItem>
          ))}
        </AnimatedList>
      )}
    </div>
  );
}

export type { RecentlyUsedItem, RecentlyUsedSectionProps };
