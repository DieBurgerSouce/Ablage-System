/**
 * ContractCalendarExport - iCal Export Dialog
 *
 * Features:
 * - Export aller Fristen als iCal-Datei
 * - Filteroptionen (Zeitraum, bestimmte Verträge)
 * - Vorschau der zu exportierenden Events
 * - Download-Button
 */

import { useState, useMemo } from 'react';
import { format, addDays } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Calendar,
  Download,
  FileText,
  Clock,
  AlertTriangle,
  Loader2,
  ExternalLink,
} from 'lucide-react';
import { useICalExport, useUpcomingDeadlines } from '../hooks/useContracts';
import type { DeadlineAlert } from '../types/contract-types';

interface ContractCalendarExportProps {
  contractIds?: string[];
  trigger?: React.ReactNode;
}

const DAYS_AHEAD_OPTIONS = [
  { value: '30', label: '30 Tage' },
  { value: '60', label: '60 Tage' },
  { value: '90', label: '90 Tage' },
  { value: '180', label: '6 Monate' },
  { value: '365', label: '1 Jahr' },
];

const urgencyConfig = {
  critical: {
    color: 'bg-red-500',
    textColor: 'text-red-700',
    label: 'Kritisch',
  },
  warning: {
    color: 'bg-orange-500',
    textColor: 'text-orange-700',
    label: 'Warnung',
  },
  upcoming: {
    color: 'bg-blue-500',
    textColor: 'text-blue-700',
    label: 'Anstehend',
  },
};

const deadlineTypeLabels: Record<string, string> = {
  notice: 'Kündigungsfrist',
  end: 'Vertragsende',
  renewal: 'Verlängerungsoption',
};

export function ContractCalendarExport({ contractIds, trigger }: ContractCalendarExportProps) {
  const [open, setOpen] = useState(false);
  const [daysAhead, setDaysAhead] = useState('90');
  const [selectedDeadlines, setSelectedDeadlines] = useState<Set<string>>(new Set());
  const [selectAll, setSelectAll] = useState(true);

  // Fristen laden
  const { data: deadlinesData, isLoading: isLoadingDeadlines } = useUpcomingDeadlines(
    parseInt(daysAhead, 10),
    { enabled: open }
  );

  // iCal Export Mutation
  const icalExport = useICalExport();

  // Gefilterte Fristen (basierend auf contractIds wenn angegeben)
  const filteredDeadlines = useMemo(() => {
    if (!deadlinesData?.items) return [];

    if (contractIds && contractIds.length > 0) {
      return deadlinesData.items.filter((d) => contractIds.includes(d.contract_id));
    }

    return deadlinesData.items;
  }, [deadlinesData, contractIds]);

  // Selektierte Fristen
  const visibleDeadlines = useMemo(() => {
    if (selectAll) {
      return filteredDeadlines;
    }
    return filteredDeadlines.filter((d) =>
      selectedDeadlines.has(`${d.contract_id}-${d.deadline_type}`)
    );
  }, [filteredDeadlines, selectAll, selectedDeadlines]);

  // Statistiken
  const stats = useMemo(() => {
    const deadlines = visibleDeadlines;
    return {
      total: deadlines.length,
      critical: deadlines.filter((d) => d.urgency === 'critical').length,
      warning: deadlines.filter((d) => d.urgency === 'warning').length,
      upcoming: deadlines.filter((d) => d.urgency === 'upcoming').length,
    };
  }, [visibleDeadlines]);

  // Toggle einzelne Frist
  const toggleDeadline = (deadline: DeadlineAlert) => {
    const key = `${deadline.contract_id}-${deadline.deadline_type}`;
    const newSelected = new Set(selectedDeadlines);
    if (newSelected.has(key)) {
      newSelected.delete(key);
    } else {
      newSelected.add(key);
    }
    setSelectedDeadlines(newSelected);
    setSelectAll(false);
  };

  // Alle auswählen/abwählen
  const handleSelectAll = (checked: boolean) => {
    setSelectAll(checked);
    if (checked) {
      setSelectedDeadlines(new Set());
    }
  };

  // Export durchführen
  const handleExport = async () => {
    await icalExport.mutateAsync({
      days_ahead: parseInt(daysAhead, 10),
      contract_ids: contractIds,
    });
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="sm">
            <Calendar className="h-4 w-4 mr-2" />
            Kalender-Export
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Kalender-Export (iCal)
          </DialogTitle>
          <DialogDescription>
            Exportieren Sie Vertragsfristen als iCal-Datei für Ihren Kalender
            (Outlook, Google Calendar, Apple Kalender).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Zeitraum-Auswahl */}
          <div className="space-y-2">
            <Label>Zeitraum</Label>
            <Select value={daysAhead} onValueChange={setDaysAhead}>
              <SelectTrigger>
                <SelectValue placeholder="Zeitraum wählen" />
              </SelectTrigger>
              <SelectContent>
                {DAYS_AHEAD_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Fristen bis {format(addDays(new Date(), parseInt(daysAhead, 10)), 'dd.MM.yyyy', { locale: de })}
            </p>
          </div>

          <Separator />

          {/* Statistik-Badges */}
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary" className="gap-1">
              <FileText className="h-3 w-3" />
              {stats.total} Termine
            </Badge>
            {stats.critical > 0 && (
              <Badge variant="destructive" className="gap-1">
                <AlertTriangle className="h-3 w-3" />
                {stats.critical} kritisch
              </Badge>
            )}
            {stats.warning > 0 && (
              <Badge variant="outline" className="text-orange-600 border-orange-300 gap-1">
                <Clock className="h-3 w-3" />
                {stats.warning} Warnung
              </Badge>
            )}
            {stats.upcoming > 0 && (
              <Badge variant="outline" className="text-blue-600 border-blue-300 gap-1">
                <Clock className="h-3 w-3" />
                {stats.upcoming} anstehend
              </Badge>
            )}
          </div>

          {/* Fristen-Auswahl */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label>Fristen auswählen</Label>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="select-all"
                  checked={selectAll}
                  onCheckedChange={(checked) => handleSelectAll(!!checked)}
                />
                <label htmlFor="select-all" className="text-sm cursor-pointer">
                  Alle auswählen
                </label>
              </div>
            </div>

            {isLoadingDeadlines ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : filteredDeadlines.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Calendar className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>Keine Fristen im gewaehlten Zeitraum</p>
              </div>
            ) : (
              <ScrollArea className="h-[200px] border rounded-md">
                <div className="p-3 space-y-2">
                  {filteredDeadlines.map((deadline) => {
                    const key = `${deadline.contract_id}-${deadline.deadline_type}`;
                    const isChecked =
                      selectAll || selectedDeadlines.has(key);
                    const config = urgencyConfig[deadline.urgency];

                    return (
                      <div
                        key={key}
                        className={`flex items-start gap-3 p-2 rounded-md hover:bg-muted/50 cursor-pointer ${
                          isChecked ? 'bg-muted/30' : ''
                        }`}
                        onClick={() => toggleDeadline(deadline)}
                      >
                        <Checkbox
                          checked={isChecked}
                          onCheckedChange={() => toggleDeadline(deadline)}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${config.color}`} />
                            <span className="text-sm font-medium truncate">
                              {deadline.contract_title}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
                            <span>{deadlineTypeLabels[deadline.deadline_type]}</span>
                            <span>-</span>
                            <span className={config.textColor}>
                              {deadline.days_remaining} Tage
                            </span>
                          </div>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {format(new Date(deadline.deadline_date), 'dd.MM.yyyy', { locale: de })}
                        </Badge>
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
            )}
          </div>

          {/* Hinweis */}
          <div className="bg-muted/50 rounded-lg p-3 space-y-2">
            <p className="text-sm font-medium">Hinweise zum iCal-Export:</p>
            <ul className="text-xs text-muted-foreground space-y-1">
              <li className="flex items-center gap-2">
                <Clock className="h-3 w-3" />
                Erinnerungen werden 7 und 1 Tag vorher erstellt
              </li>
              <li className="flex items-center gap-2">
                <ExternalLink className="h-3 w-3" />
                Die Datei kann in alle gaengigen Kalender importiert werden
              </li>
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Abbrechen
          </Button>
          <Button
            onClick={handleExport}
            disabled={icalExport.isPending || visibleDeadlines.length === 0}
          >
            {icalExport.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Exportiere...
              </>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" />
                {visibleDeadlines.length} Termine exportieren
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ContractCalendarExport;
