/**
 * Widget Config Modal
 *
 * Modal dialog for configuring individual widget settings.
 * Allows users to customize time range, filters, chart type, etc.
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Loader2, Settings, X } from 'lucide-react';
import type { WidgetSettings } from '../hooks/useWidgetConfig';

// ==================== Types ====================

interface WidgetConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  widgetId: string;
  widgetType: string;
  currentSettings?: WidgetSettings;
  onSave: (settings: WidgetSettings) => Promise<void>;
  isSaving?: boolean;
}

// Widget type metadata for configuration options
const WIDGET_CONFIG_OPTIONS: Record<
  string,
  {
    label: string;
    hasTimeRange?: boolean;
    hasChartType?: boolean;
    hasMaxItems?: boolean;
    hasFilterTags?: boolean;
    hasLegend?: boolean;
  }
> = {
  today: {
    label: 'Heute',
    hasMaxItems: true,
  },
  'system-status': {
    label: 'Systemstatus',
  },
  'finance-status': {
    label: 'Finanzen',
    hasTimeRange: true,
  },
  'quick-links': {
    label: 'Schnellzugriff',
  },
  upload: {
    label: 'Upload',
  },
  'recent-documents': {
    label: 'Letzte Dokumente',
    hasMaxItems: true,
    hasFilterTags: true,
  },
  cashflow: {
    label: 'Cashflow',
    hasTimeRange: true,
    hasChartType: true,
    hasLegend: true,
  },
  'aging-report': {
    label: 'Fälligkeitsanalyse',
    hasTimeRange: true,
    hasChartType: true,
  },
  'open-invoices': {
    label: 'Offene Rechnungen',
    hasMaxItems: true,
    hasFilterTags: true,
  },
  'activity-feed': {
    label: 'Aktivitäten',
    hasMaxItems: true,
  },
  'documents-today': {
    label: 'Dokumente heute',
    hasMaxItems: true,
  },
  'approvals-pending': {
    label: 'Ausstehende Genehmigungen',
    hasMaxItems: true,
  },
};

const TIME_RANGE_OPTIONS = [
  { value: '7d', label: '7 Tage' },
  { value: '30d', label: '30 Tage' },
  { value: '90d', label: '90 Tage' },
  { value: '1y', label: '1 Jahr' },
];

const CHART_TYPE_OPTIONS = [
  { value: 'line', label: 'Liniendiagramm' },
  { value: 'bar', label: 'Balkendiagramm' },
  { value: 'pie', label: 'Kreisdiagramm' },
];

// ==================== Component ====================

export function WidgetConfigModal({
  isOpen,
  onClose,
  widgetId,
  widgetType,
  currentSettings,
  onSave,
  isSaving = false,
}: WidgetConfigModalProps) {
  const [settings, setSettings] = useState<WidgetSettings>({});
  const [tagInput, setTagInput] = useState('');

  const widgetMeta = WIDGET_CONFIG_OPTIONS[widgetType] || {
    label: widgetType,
  };

  // Initialize settings when modal opens
  useEffect(() => {
    if (isOpen && currentSettings) {
      setSettings(currentSettings);
    } else if (isOpen) {
      setSettings({});
    }
  }, [isOpen, currentSettings]);

  const handleSave = async () => {
    await onSave(settings);
    onClose();
  };

  const handleAddTag = () => {
    const tag = tagInput.trim().toLowerCase();
    if (tag && !settings.filterTags?.includes(tag)) {
      setSettings((prev) => ({
        ...prev,
        filterTags: [...(prev.filterTags || []), tag],
      }));
    }
    setTagInput('');
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setSettings((prev) => ({
      ...prev,
      filterTags: prev.filterTags?.filter((t) => t !== tagToRemove) || [],
    }));
  };

  const hasAnyOptions =
    widgetMeta.hasTimeRange ||
    widgetMeta.hasChartType ||
    widgetMeta.hasMaxItems ||
    widgetMeta.hasFilterTags ||
    widgetMeta.hasLegend;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Widget konfigurieren
          </DialogTitle>
          <DialogDescription>
            Einstellungen für &quot;{widgetMeta.label}&quot; anpassen
          </DialogDescription>
        </DialogHeader>

        {hasAnyOptions ? (
          <div className="grid gap-4 py-4">
            {/* Time Range */}
            {widgetMeta.hasTimeRange && (
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="timeRange" className="text-right">
                  Zeitraum
                </Label>
                <Select
                  value={settings.timeRange || '30d'}
                  onValueChange={(value) =>
                    setSettings((prev) => ({
                      ...prev,
                      timeRange: value as WidgetSettings['timeRange'],
                    }))
                  }
                >
                  <SelectTrigger className="col-span-3">
                    <SelectValue placeholder="Zeitraum wählen" />
                  </SelectTrigger>
                  <SelectContent>
                    {TIME_RANGE_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Chart Type */}
            {widgetMeta.hasChartType && (
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="chartType" className="text-right">
                  Diagramm
                </Label>
                <Select
                  value={settings.chartType || 'line'}
                  onValueChange={(value) =>
                    setSettings((prev) => ({
                      ...prev,
                      chartType: value as WidgetSettings['chartType'],
                    }))
                  }
                >
                  <SelectTrigger className="col-span-3">
                    <SelectValue placeholder="Diagrammtyp wählen" />
                  </SelectTrigger>
                  <SelectContent>
                    {CHART_TYPE_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Max Items */}
            {widgetMeta.hasMaxItems && (
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="maxItems" className="text-right">
                  Max. Einträge
                </Label>
                <Input
                  id="maxItems"
                  type="number"
                  min={5}
                  max={50}
                  className="col-span-3"
                  value={settings.maxItems || 10}
                  onChange={(e) =>
                    setSettings((prev) => ({
                      ...prev,
                      maxItems: Math.min(50, Math.max(5, parseInt(e.target.value) || 10)),
                    }))
                  }
                />
              </div>
            )}

            {/* Show Legend */}
            {widgetMeta.hasLegend && (
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="showLegend" className="text-right">
                  Legende
                </Label>
                <div className="col-span-3 flex items-center gap-2">
                  <Switch
                    id="showLegend"
                    checked={settings.showLegend ?? true}
                    onCheckedChange={(checked) =>
                      setSettings((prev) => ({
                        ...prev,
                        showLegend: checked,
                      }))
                    }
                  />
                  <span className="text-sm text-muted-foreground">
                    {settings.showLegend !== false ? 'Sichtbar' : 'Versteckt'}
                  </span>
                </div>
              </div>
            )}

            {/* Filter Tags */}
            {widgetMeta.hasFilterTags && (
              <div className="grid grid-cols-4 items-start gap-4">
                <Label htmlFor="filterTags" className="text-right pt-2">
                  Filter-Tags
                </Label>
                <div className="col-span-3 space-y-2">
                  <div className="flex gap-2">
                    <Input
                      id="filterTags"
                      placeholder="Tag eingeben..."
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          handleAddTag();
                        }
                      }}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleAddTag}
                      disabled={!tagInput.trim()}
                    >
                      +
                    </Button>
                  </div>
                  {settings.filterTags && settings.filterTags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {settings.filterTags.map((tag) => (
                        <Badge
                          key={tag}
                          variant="secondary"
                          className="gap-1 cursor-pointer"
                          onClick={() => handleRemoveTag(tag)}
                        >
                          {tag}
                          <X className="h-3 w-3" />
                        </Badge>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Nur Dokumente mit diesen Tags anzeigen
                  </p>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="py-6 text-center text-muted-foreground">
            <p>Dieses Widget hat keine konfigurierbaren Optionen.</p>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSaving}>
            Abbrechen
          </Button>
          {hasAnyOptions && (
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Speichern...
                </>
              ) : (
                'Speichern'
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
