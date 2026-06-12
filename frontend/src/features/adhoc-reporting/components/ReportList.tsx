/**
 * ReportList Component
 * German Enterprise Document Platform
 */

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
  FileText,
  Play,
  Edit2,
  Trash2,
  Share2,
  Download,
  Calendar,
  MoreVertical,
} from 'lucide-react';
import type { ReportDefinition } from '../types/adhoc-reporting-types';
import { DATA_SOURCE_LABELS } from '../types/adhoc-reporting-types';

interface ReportListProps {
  reports: ReportDefinition[];
  isLoading?: boolean;
  onExecute?: (reportId: number) => void;
  onEdit?: (reportId: number) => void;
  onDelete?: (reportId: number) => void;
  onShare?: (reportId: number) => void;
  onExport?: (reportId: number) => void;
  onSchedule?: (reportId: number) => void;
}

export function ReportList({
  reports,
  isLoading = false,
  onExecute,
  onEdit,
  onDelete,
  onShare,
  onExport,
  onSchedule,
}: ReportListProps) {
  if (isLoading) {
    return (
      <Card>
        <div className="p-4 space-y-3">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      </Card>
    );
  }

  if (reports.length === 0) {
    return (
      <Card className="p-12 text-center">
        <FileText className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
        <h3 className="text-lg font-semibold mb-2">Keine Reports vorhanden</h3>
        <p className="text-muted-foreground mb-4">
          Erstellen Sie Ihren ersten Ad-Hoc Report
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Datenquelle</TableHead>
            <TableHead>Erstellt</TableHead>
            <TableHead>Zuletzt ausgeführt</TableHead>
            <TableHead className="text-right">Aktionen</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reports.map((report) => (
            <TableRow key={report.id}>
              <TableCell>
                <div>
                  <div className="font-medium">{report.name}</div>
                  {report.description && (
                    <div className="text-xs text-muted-foreground line-clamp-1">
                      {report.description}
                    </div>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <Badge variant="secondary">
                  {DATA_SOURCE_LABELS[report.data_source] || report.data_source}
                </Badge>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {report.created_at
                  ? new Date(report.created_at).toLocaleDateString('de-DE')
                  : '-'}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {report.last_executed_at
                  ? new Date(report.last_executed_at).toLocaleDateString('de-DE')
                  : 'Noch nie'}
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end space-x-2">
                  {onExecute && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onExecute(report.id!)}
                      title="Report ausführen"
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                  )}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm">
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {onEdit && (
                        <DropdownMenuItem onClick={() => onEdit(report.id!)}>
                          <Edit2 className="h-4 w-4 mr-2" />
                          Bearbeiten
                        </DropdownMenuItem>
                      )}
                      {onShare && (
                        <DropdownMenuItem onClick={() => onShare(report.id!)}>
                          <Share2 className="h-4 w-4 mr-2" />
                          Freigeben
                        </DropdownMenuItem>
                      )}
                      {onExport && (
                        <DropdownMenuItem onClick={() => onExport(report.id!)}>
                          <Download className="h-4 w-4 mr-2" />
                          Exportieren
                        </DropdownMenuItem>
                      )}
                      {onSchedule && (
                        <DropdownMenuItem onClick={() => onSchedule(report.id!)}>
                          <Calendar className="h-4 w-4 mr-2" />
                          Zeitplan
                        </DropdownMenuItem>
                      )}
                      {onDelete && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            onClick={() => onDelete(report.id!)}
                            className="text-destructive"
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Löschen
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
