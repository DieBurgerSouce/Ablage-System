/**
 * Widget Palette Component
 *
 * Sidebar mit verfügbaren Widgets zum Hinzufügen
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  FileText,
  Receipt,
  TrendingUp,
  Users,
  BarChart3,
  Workflow,
  Shield,
  Search,
  Plus,
} from 'lucide-react';
import { useAvailableWidgets } from '../hooks/useDashboards';
import type { WidgetDefinition, WidgetType } from '../types';

interface WidgetPaletteProps {
  onAddWidget: (type: WidgetType, title: string) => void;
  isOpen: boolean;
}

const CATEGORY_ICONS = {
  documents: FileText,
  finance: Receipt,
  workflows: Workflow,
  analytics: BarChart3,
};

const CATEGORY_LABELS = {
  documents: 'Dokumente',
  finance: 'Finanzen',
  workflows: 'Workflows',
  analytics: 'Analyse',
};

const WIDGET_ICONS: Record<WidgetType, any> = {
  document_count: FileText,
  invoice_summary: Receipt,
  ocr_quality: BarChart3,
  entity_list: Users,
  cashflow_chart: TrendingUp,
  recent_documents: FileText,
  risk_overview: Shield,
  workflow_status: Workflow,
  custom_chart: BarChart3,
};

export function WidgetPalette({ onAddWidget, isOpen }: WidgetPaletteProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const { data: widgets = [], isLoading } = useAvailableWidgets();

  const filteredWidgets = widgets.filter(
    (widget) =>
      widget.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      widget.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const widgetsByCategory = filteredWidgets.reduce((acc, widget) => {
    if (!acc[widget.category]) {
      acc[widget.category] = [];
    }
    acc[widget.category].push(widget);
    return acc;
  }, {} as Record<string, WidgetDefinition[]>);

  const handleAddWidget = (widget: WidgetDefinition) => {
    onAddWidget(widget.type, widget.name);
  };

  if (!isOpen) return null;

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Widget hinzufügen</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-3 p-4 pt-0">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Widget suchen..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <ScrollArea className="flex-1 -mx-4 px-4">
          {isLoading ? (
            <div className="text-sm text-muted-foreground text-center py-8">
              Lädt Widgets...
            </div>
          ) : Object.keys(widgetsByCategory).length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-8">
              Keine Widgets gefunden
            </div>
          ) : (
            <Accordion type="multiple" defaultValue={Object.keys(widgetsByCategory)}>
              {Object.entries(widgetsByCategory).map(([category, categoryWidgets]) => {
                const Icon = CATEGORY_ICONS[category as keyof typeof CATEGORY_ICONS];
                return (
                  <AccordionItem key={category} value={category}>
                    <AccordionTrigger className="hover:no-underline">
                      <div className="flex items-center gap-2">
                        {Icon && <Icon className="h-4 w-4" />}
                        <span>{CATEGORY_LABELS[category as keyof typeof CATEGORY_LABELS]}</span>
                        <Badge variant="secondary" className="ml-2">
                          {categoryWidgets.length}
                        </Badge>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="space-y-2 pt-2">
                      {categoryWidgets.map((widget) => {
                        const WidgetIcon = WIDGET_ICONS[widget.type];
                        return (
                          <div
                            key={widget.type}
                            className="group relative p-3 rounded-lg border hover:border-primary hover:shadow-sm transition-all cursor-move"
                            draggable
                            onDragStart={(e) => {
                              e.dataTransfer.effectAllowed = 'copy';
                              e.dataTransfer.setData(
                                'application/json',
                                JSON.stringify(widget)
                              );
                            }}
                          >
                            <div className="flex items-start gap-3">
                              <div className="p-2 rounded bg-primary/10">
                                <WidgetIcon className="h-4 w-4 text-primary" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="font-medium text-sm">
                                  {widget.name}
                                </div>
                                <div className="text-xs text-muted-foreground mt-0.5">
                                  {widget.description}
                                </div>
                                <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                                  <span>
                                    {widget.defaultSize.w}x{widget.defaultSize.h}
                                  </span>
                                </div>
                              </div>
                            </div>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                              onClick={() => handleAddWidget(widget)}
                            >
                              <Plus className="h-4 w-4" />
                            </Button>
                          </div>
                        );
                      })}
                    </AccordionContent>
                  </AccordionItem>
                );
              })}
            </Accordion>
          )}
        </ScrollArea>

        <div className="pt-3 border-t text-xs text-muted-foreground">
          <p>Ziehen Sie Widgets in das Dashboard oder klicken Sie auf +</p>
        </div>
      </CardContent>
    </Card>
  );
}
