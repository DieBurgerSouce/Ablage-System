/**
 * DeadlineList - Fristen-Übersicht
 *
 * Liste aller Fristen mit Status und Erinnerungen
 */

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  MoreHorizontal,
  Calendar,
  Edit,
  Trash2,
  CheckCircle,
  Search,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Clock,
  Filter,
  Download,
  RefreshCw,
  Bell,
} from 'lucide-react';
import type { PrivatDeadlineWithStatus, PrivatDeadlineType } from '@/types/privat';
import { cn } from '@/lib/utils';

interface DeadlineListProps {
  deadlines: PrivatDeadlineWithStatus[];
  total: number;
  page: number;
  pageSize: number;
  isLoading?: boolean;
  error?: Error | null;
  onPageChange?: (page: number) => void;
  onSelect?: (deadline: PrivatDeadlineWithStatus) => void;
  onEdit?: (deadline: PrivatDeadlineWithStatus) => void;
  onDelete?: (deadline: PrivatDeadlineWithStatus) => void;
  onComplete?: (deadline: PrivatDeadlineWithStatus) => void;
  onCreate?: () => void;
  onExportCalendar?: () => void;
  onSearch?: (query: string) => void;
  onTypeFilter?: (type: PrivatDeadlineType | 'all') => void;
  onShowCompleted?: (show: boolean) => void;
  selectedType?: PrivatDeadlineType | 'all';
  searchQuery?: string;
  showCompleted?: boolean;
  className?: string;
}

const DEADLINE_TYPES: { value: PrivatDeadlineType | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'insurance_payment', label: 'Versicherungszahlung' },
  { value: 'loan_payment', label: 'Kreditrate' },
  { value: 'tax_deadline', label: 'Steuerfrist' },
  { value: 'contract_renewal', label: 'Vertragsverlängerung' },
  { value: 'vehicle_inspection', label: 'Fahrzeugprüfung' },
  { value: 'registration_renewal', label: 'Anmeldung erneuern' },
  { value: 'custom', label: 'Benutzerdefiniert' },
];

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    weekday: 'short',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const getDeadlineTypeLabel = (type: PrivatDeadlineType): string => {
  const found = DEADLINE_TYPES.find((t) => t.value === type);
  return found?.label || type;
};

const getDeadlineTypeColor = (type: PrivatDeadlineType): string => {
  const colors: Record<PrivatDeadlineType, string> = {
    insurance_payment: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    loan_payment: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200',
    tax_deadline: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    contract_renewal: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    vehicle_inspection: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
    registration_renewal: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    custom: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200',
  };
  return colors[type];
};

const getStatusBadge = (deadline: PrivatDeadlineWithStatus): React.ReactNode => {
  if (deadline.isCompleted) {
    return (
      <Badge variant="secondary" className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
        <CheckCircle className="h-3 w-3 mr-1" />
        Erledigt
      </Badge>
    );
  }

  if (deadline.isOverdue) {
    return (
      <Badge variant="destructive">
        <AlertTriangle className="h-3 w-3 mr-1" />
        Überfällig
      </Badge>
    );
  }

  if (deadline.daysRemaining <= 3) {
    return (
      <Badge variant="secondary" className="bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
        <Clock className="h-3 w-3 mr-1" />
        {deadline.daysRemaining} {deadline.daysRemaining === 1 ? 'Tag' : 'Tage'}
      </Badge>
    );
  }

  if (deadline.daysRemaining <= 7) {
    return (
      <Badge variant="secondary" className="bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
        <Clock className="h-3 w-3 mr-1" />
        {deadline.daysRemaining} Tage
      </Badge>
    );
  }

  return (
    <Badge variant="outline">
      <Clock className="h-3 w-3 mr-1" />
      {deadline.daysRemaining} Tage
    </Badge>
  );
};

export function DeadlineList({
  deadlines,
  total,
  page,
  pageSize,
  isLoading,
  error,
  onPageChange,
  onSelect,
  onEdit,
  onDelete,
  onComplete,
  onCreate,
  onExportCalendar,
  onSearch,
  onTypeFilter,
  onShowCompleted,
  selectedType = 'all',
  searchQuery = '',
  showCompleted = false,
  className,
}: DeadlineListProps) {
  const totalPages = Math.ceil(total / pageSize);

  // Count by status
  const overdueCount = deadlines.filter((d) => d.isOverdue && !d.isCompleted).length;

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Fristen</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Fristen
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-950">
            <Calendar className="h-6 w-6 text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Fristen</h1>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>{total} Fristen</span>
              {overdueCount > 0 && (
                <Badge variant="destructive" className="text-xs">
                  {overdueCount} überfällig
                </Badge>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onExportCalendar && (
            <Button variant="outline" onClick={onExportCalendar}>
              <Download className="mr-2 h-4 w-4" />
              iCal Export
            </Button>
          )}
          {onCreate && (
            <Button onClick={onCreate}>
              <Plus className="mr-2 h-4 w-4" />
              Neue Frist
            </Button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Fristen suchen..."
            value={searchQuery}
            onChange={(e) => onSearch?.(e.target.value)}
            className="pl-8"
          />
        </div>
        <Select
          value={selectedType}
          onValueChange={(v) => onTypeFilter?.(v as PrivatDeadlineType | 'all')}
        >
          <SelectTrigger className="w-[200px]">
            <Filter className="mr-2 h-4 w-4" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DEADLINE_TYPES.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                {type.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2 px-3 border rounded-md">
          <Checkbox
            id="showCompleted"
            checked={showCompleted}
            onCheckedChange={(checked) => onShowCompleted?.(checked as boolean)}
          />
          <label htmlFor="showCompleted" className="text-sm cursor-pointer">
            Erledigte anzeigen
          </label>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : deadlines.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Calendar className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium mb-2">Keine Fristen</h3>
            <p className="text-muted-foreground text-center mb-4">
              Erstellen Sie Fristen, um wichtige Termine nicht zu vergessen.
            </p>
            {onCreate && (
              <Button onClick={onCreate}>
                <Plus className="mr-2 h-4 w-4" />
                Frist erstellen
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="space-y-3">
            {deadlines.map((deadline) => (
              <DeadlineItem
                key={deadline.id}
                deadline={deadline}
                onSelect={onSelect}
                onEdit={onEdit}
                onDelete={onDelete}
                onComplete={onComplete}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <div className="text-sm text-muted-foreground">
                Seite {page + 1} von {totalPages}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPageChange?.(Math.max(0, page - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Zurück
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPageChange?.(Math.min(totalPages - 1, page + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Weiter
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface DeadlineItemProps {
  deadline: PrivatDeadlineWithStatus;
  onSelect?: (deadline: PrivatDeadlineWithStatus) => void;
  onEdit?: (deadline: PrivatDeadlineWithStatus) => void;
  onDelete?: (deadline: PrivatDeadlineWithStatus) => void;
  onComplete?: (deadline: PrivatDeadlineWithStatus) => void;
}

function DeadlineItem({
  deadline,
  onSelect,
  onEdit,
  onDelete,
  onComplete,
}: DeadlineItemProps) {
  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow',
        onSelect && 'cursor-pointer',
        deadline.isCompleted && 'opacity-60',
        deadline.isOverdue && !deadline.isCompleted && 'border-red-500/50'
      )}
      onClick={() => onSelect?.(deadline)}
    >
      <CardContent className="flex items-center gap-4 p-4">
        {/* Complete Checkbox */}
        {onComplete && !deadline.isCompleted && (
          <div onClick={(e) => e.stopPropagation()}>
            <Checkbox
              checked={deadline.isCompleted}
              onCheckedChange={() => onComplete(deadline)}
              className="h-5 w-5"
            />
          </div>
        )}
        {deadline.isCompleted && (
          <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0" />
        )}

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4
              className={cn(
                'font-medium truncate',
                deadline.isCompleted && 'line-through text-muted-foreground'
              )}
            >
              {deadline.title}
            </h4>
            <Badge
              variant="secondary"
              className={cn('flex-shrink-0', getDeadlineTypeColor(deadline.deadlineType))}
            >
              {getDeadlineTypeLabel(deadline.deadlineType)}
            </Badge>
            {deadline.isRecurring && (
              <Badge variant="outline" className="flex-shrink-0">
                <RefreshCw className="h-3 w-3 mr-1" />
                Wiederkehrend
              </Badge>
            )}
          </div>
          {deadline.description && (
            <p className="text-sm text-muted-foreground line-clamp-1">
              {deadline.description}
            </p>
          )}
          {deadline.relatedEntityName && (
            <p className="text-sm text-muted-foreground">
              Zugehörig zu: {deadline.relatedEntityName}
            </p>
          )}
        </div>

        {/* Date and Status */}
        <div className="flex items-center gap-4 flex-shrink-0">
          <div className="text-right">
            <p className="text-sm font-medium">{formatDate(deadline.dueDate)}</p>
            {deadline.reminderDays && deadline.reminderDays.length > 0 && (
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                <Bell className="h-3 w-3" />
                Erinnerung: {deadline.reminderDays.join(', ')} Tage vorher
              </p>
            )}
          </div>
          {getStatusBadge(deadline)}
        </div>

        {/* Actions */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
            <Button variant="ghost" size="icon" className="h-8 w-8 flex-shrink-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {onComplete && !deadline.isCompleted && (
              <DropdownMenuItem onClick={() => onComplete(deadline)}>
                <CheckCircle className="mr-2 h-4 w-4" />
                Als erledigt markieren
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => onEdit?.(deadline)}>
              <Edit className="mr-2 h-4 w-4" />
              Bearbeiten
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => onDelete?.(deadline)}
              className="text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Löschen
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </CardContent>
    </Card>
  );
}

export default DeadlineList;
