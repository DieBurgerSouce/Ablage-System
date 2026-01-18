/**
 * WidgetCatalogDrawer - Widget-Katalog Seitenleiste
 *
 * Sheet-Komponente die von rechts einschiebt und alle verfuegbaren
 * Widgets zum Hinzufuegen anzeigt.
 *
 * Features:
 * - Auflistung aller Widgets aus WIDGET_REGISTRY
 * - Anzeige ob Widget bereits aktiv
 * - Filterung nach Kategorie
 * - Hinzufuegen zum Dashboard
 */

import { useState, useMemo } from 'react';
import { LayoutGrid, Info, Zap, Database, Wallet } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { WIDGET_REGISTRY, getWidgetDefinition } from '../registry';
import { useDashboardStore } from '../stores/useDashboardStore';
import { normalizeWidgetType } from '../registry';
import { WidgetPreviewCard } from './WidgetPreviewCard';
import { toast } from 'sonner';

interface WidgetCatalogDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type CategoryFilter = 'all' | 'info' | 'action' | 'data' | 'finance';

const CATEGORY_TABS: { value: CategoryFilter; label: string; icon: React.ElementType }[] = [
  { value: 'all', label: 'Alle', icon: LayoutGrid },
  { value: 'info', label: 'Info', icon: Info },
  { value: 'action', label: 'Aktion', icon: Zap },
  { value: 'data', label: 'Daten', icon: Database },
  { value: 'finance', label: 'Finanzen', icon: Wallet },
];

export function WidgetCatalogDrawer({ open, onOpenChange }: WidgetCatalogDrawerProps) {
  const { widgets, addWidget } = useDashboardStore();
  const [category, setCategory] = useState<CategoryFilter>('all');

  // Get list of currently active widget types (normalized)
  const activeTypes = useMemo(() => {
    return new Set(widgets.map((w) => normalizeWidgetType(w.type)));
  }, [widgets]);

  // Filter widgets by category
  const filteredWidgets = useMemo(() => {
    return Object.entries(WIDGET_REGISTRY).filter(([key, def]) => {
      // Skip legacy uppercase keys
      if (key === key.toUpperCase()) return false;
      if (category === 'all') return true;
      return def?.category === category;
    });
  }, [category]);

  const handleAddWidget = (type: string) => {
    const normalizedType = normalizeWidgetType(type);
    const widgetDef = getWidgetDefinition(normalizedType);
    const size = widgetDef?.defaultSize ?? { w: 4, h: 3 };

    addWidget(normalizedType, size);
    toast.success('Widget hinzugefuegt', {
      description: `${widgetDef?.label || type} wurde zum Dashboard hinzugefuegt.`,
    });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg flex flex-col">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <LayoutGrid className="h-5 w-5" />
            Widget-Katalog
          </SheetTitle>
          <SheetDescription>
            Wählen Sie Widgets aus, um sie Ihrem Dashboard hinzuzufügen.
            Sie können mehrere Instanzen des gleichen Widgets hinzufügen.
          </SheetDescription>
        </SheetHeader>

        <Tabs
          defaultValue="all"
          value={category}
          onValueChange={(v) => setCategory(v as CategoryFilter)}
          className="flex-1 flex flex-col mt-4"
        >
          <TabsList className="grid grid-cols-5 w-full">
            {CATEGORY_TABS.map((tab) => (
              <TabsTrigger
                key={tab.value}
                value={tab.value}
                className="flex items-center gap-1.5"
              >
                <tab.icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{tab.label}</span>
              </TabsTrigger>
            ))}
          </TabsList>

          <ScrollArea className="flex-1 mt-4">
            <div className="space-y-3 pr-4">
              {filteredWidgets.map(([type, definition]) => (
                <WidgetPreviewCard
                  key={type}
                  type={type}
                  definition={definition}
                  isAdded={activeTypes.has(type)}
                  onAdd={handleAddWidget}
                />
              ))}

              {filteredWidgets.length === 0 && (
                <div className="py-8 text-center text-muted-foreground">
                  Keine Widgets in dieser Kategorie.
                </div>
              )}
            </div>
          </ScrollArea>
        </Tabs>

        <div className="pt-4 border-t mt-4">
          <p className="text-xs text-muted-foreground text-center">
            {widgets.length} Widget{widgets.length !== 1 ? 's' : ''} aktiv auf Ihrem Dashboard
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export default WidgetCatalogDrawer;
