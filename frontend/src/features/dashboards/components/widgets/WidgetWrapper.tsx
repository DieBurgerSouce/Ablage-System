/**
 * Widget Wrapper Component
 *
 * Wrapper für alle Dashboard-Widgets mit Header und Controls
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { MoreVertical, Settings, Trash2 } from 'lucide-react';
import type { ReactNode } from 'react';

interface WidgetWrapperProps {
  title: string;
  children: ReactNode;
  onRemove?: () => void;
  onSettings?: () => void;
  isEditing?: boolean;
  className?: string;
}

export function WidgetWrapper({
  title,
  children,
  onRemove,
  onSettings,
  isEditing = false,
  className = '',
}: WidgetWrapperProps) {
  return (
    <Card className={`h-full flex flex-col ${className}`}>
      <CardHeader className="pb-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold">{title}</CardTitle>
          {isEditing && (onRemove || onSettings) && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {onSettings && (
                  <DropdownMenuItem onClick={onSettings}>
                    <Settings className="h-4 w-4 mr-2" />
                    Einstellungen
                  </DropdownMenuItem>
                )}
                {onRemove && (
                  <DropdownMenuItem
                    onClick={onRemove}
                    className="text-destructive"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Entfernen
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-auto">{children}</CardContent>
    </Card>
  );
}
