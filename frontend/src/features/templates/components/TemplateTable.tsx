/**
 * TemplateTable - Vorlagen-Tabelle mit Sortierung und Aktionen
 *
 * Features:
 * - Sortierbare Spalten
 * - Kategorie-Badges mit Farbcodierung
 * - Inline-Aktionen
 * - Responsive Design
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  MoreHorizontal,
  Eye,
  Edit,
  Trash2,
  FileText,
  Copy,
  Star,
  StarOff,
} from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { Template } from '../types/template-types';
import {
  TemplateCategory,
  TemplateOutputFormat,
  TEMPLATE_CATEGORY_LABELS,
  OUTPUT_FORMAT_LABELS,
} from '../types/template-types';

interface TemplateTableProps {
  templates: Template[];
  isLoading: boolean;
  onView: (template: Template) => void;
  onEdit: (template: Template) => void;
  onDelete: (template: Template) => void;
  onGenerate: (template: Template) => void;
  onDuplicate?: (template: Template) => void;
  onSetDefault?: (template: Template) => void;
}

const categoryConfig: Record<
  TemplateCategory,
  { color: string; className?: string }
> = {
  [TemplateCategory.INVOICE]: { color: 'bg-blue-500' },
  [TemplateCategory.OFFER]: { color: 'bg-green-500' },
  [TemplateCategory.CONTRACT]: { color: 'bg-purple-500' },
  [TemplateCategory.LETTER]: { color: 'bg-gray-500' },
  [TemplateCategory.REMINDER]: { color: 'bg-yellow-500' },
  [TemplateCategory.DUNNING]: { color: 'bg-red-500' },
  [TemplateCategory.CONFIRMATION]: { color: 'bg-teal-500' },
  [TemplateCategory.REPORT]: { color: 'bg-indigo-500' },
  [TemplateCategory.CERTIFICATE]: { color: 'bg-amber-500' },
  [TemplateCategory.OTHER]: { color: 'bg-slate-500' },
};

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return format(new Date(dateString), 'dd.MM.yyyy', { locale: de });
}

export function TemplateTable({
  templates,
  isLoading,
  onView,
  onEdit,
  onDelete,
  onGenerate,
  onDuplicate,
  onSetDefault,
}: TemplateTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  if (templates.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
        <p>Keine Vorlagen gefunden</p>
        <p className="text-sm mt-1">Erstellen Sie eine neue Vorlage um zu beginnen.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[120px]">Code</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Kategorie</TableHead>
            <TableHead>Format</TableHead>
            <TableHead className="text-center">Variablen</TableHead>
            <TableHead className="text-center">Version</TableHead>
            <TableHead className="text-right">Nutzungen</TableHead>
            <TableHead>Zuletzt verwendet</TableHead>
            <TableHead className="w-[50px]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {templates.map((template) => {
            const categoryConf = categoryConfig[template.category as TemplateCategory];

            return (
              <TableRow
                key={template.id}
                className="cursor-pointer"
                onClick={() => onView(template)}
              >
                <TableCell className="font-mono text-sm">
                  <div className="flex items-center gap-2">
                    {template.is_default && (
                      <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                    )}
                    {template.code}
                  </div>
                </TableCell>
                <TableCell className="font-medium max-w-[250px] truncate">
                  {template.name}
                  {template.description && (
                    <p className="text-xs text-muted-foreground truncate">
                      {template.description}
                    </p>
                  )}
                </TableCell>
                <TableCell>
                  <Badge className={categoryConf?.color}>
                    {TEMPLATE_CATEGORY_LABELS[template.category as TemplateCategory] ||
                      template.category}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {OUTPUT_FORMAT_LABELS[template.output_format as TemplateOutputFormat] ||
                    template.output_format.toUpperCase()}
                </TableCell>
                <TableCell className="text-center text-sm">
                  {template.variables?.length || 0}
                </TableCell>
                <TableCell className="text-center text-sm font-mono">
                  v{template.version}
                </TableCell>
                <TableCell className="text-right text-sm">
                  {template.usage_count.toLocaleString('de-DE')}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {formatDate(template.last_used_at)}
                </TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">Aktionen</span>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => onView(template)}>
                        <Eye className="h-4 w-4 mr-2" />
                        Anzeigen
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onEdit(template)}>
                        <Edit className="h-4 w-4 mr-2" />
                        Bearbeiten
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => onGenerate(template)}>
                        <FileText className="h-4 w-4 mr-2" />
                        Dokument erstellen
                      </DropdownMenuItem>
                      {onDuplicate && (
                        <DropdownMenuItem onClick={() => onDuplicate(template)}>
                          <Copy className="h-4 w-4 mr-2" />
                          Duplizieren
                        </DropdownMenuItem>
                      )}
                      {onSetDefault && !template.is_default && (
                        <DropdownMenuItem onClick={() => onSetDefault(template)}>
                          <Star className="h-4 w-4 mr-2" />
                          Als Standard setzen
                        </DropdownMenuItem>
                      )}
                      {onSetDefault && template.is_default && (
                        <DropdownMenuItem onClick={() => onSetDefault(template)}>
                          <StarOff className="h-4 w-4 mr-2" />
                          Standard entfernen
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={() => onDelete(template)}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Loeschen
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
