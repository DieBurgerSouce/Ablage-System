// Generic Widget Container Component
// Configurable wrapper with title, actions menu (maximize, configure, remove)

import { ReactNode, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Maximize2, Settings, Trash2, MoreVertical } from 'lucide-react';
import { cn } from '@/lib/utils';
import { UI_LABELS } from '../types/smart-dashboard-types';

interface WidgetContainerProps {
  title: string;
  children: ReactNode;
  widgetId?: string;
  className?: string;
  onMaximize?: () => void;
  onConfigure?: () => void;
  onRemove?: () => void;
  showActions?: boolean;
}

export function WidgetContainer({
  title,
  children,
  widgetId,
  className,
  onMaximize,
  onConfigure,
  onRemove,
  showActions = true,
}: WidgetContainerProps) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <Card
      className={cn('relative hover:shadow-md transition-shadow', className)}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-lg font-semibold">{title}</CardTitle>

        {showActions && (isHovered || window.innerWidth < 768) && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {onMaximize && (
                <DropdownMenuItem onClick={onMaximize}>
                  <Maximize2 className="mr-2 h-4 w-4" />
                  {UI_LABELS.ACTION_MAXIMIZE}
                </DropdownMenuItem>
              )}
              {onConfigure && (
                <DropdownMenuItem onClick={onConfigure}>
                  <Settings className="mr-2 h-4 w-4" />
                  {UI_LABELS.ACTION_CONFIGURE}
                </DropdownMenuItem>
              )}
              {onRemove && (
                <DropdownMenuItem onClick={onRemove} className="text-destructive">
                  <Trash2 className="mr-2 h-4 w-4" />
                  {UI_LABELS.ACTION_REMOVE}
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </CardHeader>

      <CardContent>{children}</CardContent>
    </Card>
  );
}
