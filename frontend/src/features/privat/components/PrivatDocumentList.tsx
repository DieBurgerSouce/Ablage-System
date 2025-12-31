/**
 * PrivatDocumentList - Dokumentenliste mit Filter und Aktionen
 *
 * Zeigt Dokumente eines Ordners oder Space mit Suchfunktion
 */

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  MoreHorizontal,
  Eye,
  Edit,
  Download,
  Trash2,
  Filter,
  Search,
  FileText,
  File,
  Lock,
  ChevronLeft,
  ChevronRight,
  Upload,
  Grid,
  List,
} from 'lucide-react';
import type { PrivatDocument, PrivatDocumentType } from '@/types/privat';
import { cn } from '@/lib/utils';

interface PrivatDocumentListProps {
  documents: PrivatDocument[];
  total: number;
  page: number;
  pageSize: number;
  isLoading?: boolean;
  error?: Error | null;
  onPageChange?: (page: number) => void;
  onSelect?: (doc: PrivatDocument) => void;
  onEdit?: (doc: PrivatDocument) => void;
  onDownload?: (doc: PrivatDocument) => void;
  onDelete?: (doc: PrivatDocument) => void;
  onCreate?: () => void;
  onSearch?: (query: string) => void;
  onTypeFilter?: (type: PrivatDocumentType | 'all') => void;
  selectedType?: PrivatDocumentType | 'all';
  searchQuery?: string;
  className?: string;
}

const DOCUMENT_TYPES: { value: PrivatDocumentType | 'all'; label: string }[] = [
  { value: 'all', label: 'Alle Typen' },
  { value: 'contract', label: 'Vertrag' },
  { value: 'invoice', label: 'Rechnung' },
  { value: 'receipt', label: 'Quittung' },
  { value: 'certificate', label: 'Zertifikat' },
  { value: 'insurance_policy', label: 'Versicherungspolice' },
  { value: 'tax_document', label: 'Steuerdokument' },
  { value: 'correspondence', label: 'Korrespondenz' },
  { value: 'photo', label: 'Foto' },
  { value: 'other', label: 'Sonstiges' },
];

const getTypeLabel = (type: PrivatDocumentType): string => {
  const found = DOCUMENT_TYPES.find((t) => t.value === type);
  return found?.label || type;
};

const getTypeColor = (type: PrivatDocumentType): string => {
  switch (type) {
    case 'contract':
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
    case 'invoice':
      return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
    case 'receipt':
      return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
    case 'certificate':
      return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200';
    case 'insurance_policy':
      return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
    case 'tax_document':
      return 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200';
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
  }
};

const formatBytes = (bytes?: number): string => {
  if (!bytes) return '-';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

export function PrivatDocumentList({
  documents,
  total,
  page,
  pageSize,
  isLoading,
  error,
  onPageChange,
  onSelect,
  onEdit,
  onDownload,
  onDelete,
  onCreate,
  onSearch,
  onTypeFilter,
  selectedType = 'all',
  searchQuery = '',
  className,
}: PrivatDocumentListProps) {
  const [viewMode, setViewMode] = React.useState<'list' | 'grid'>('list');
  const totalPages = Math.ceil(total / pageSize);

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Dokumente</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Dokumente
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Dokumente</CardTitle>
            <CardDescription>
              {total} {total === 1 ? 'Dokument' : 'Dokumente'}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={viewMode === 'list' ? 'secondary' : 'ghost'}
              size="icon"
              onClick={() => setViewMode('list')}
            >
              <List className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === 'grid' ? 'secondary' : 'ghost'}
              size="icon"
              onClick={() => setViewMode('grid')}
            >
              <Grid className="h-4 w-4" />
            </Button>
            {onCreate && (
              <Button onClick={onCreate}>
                <Upload className="mr-2 h-4 w-4" />
                Hochladen
              </Button>
            )}
          </div>
        </div>

        {/* Filter */}
        <div className="flex flex-wrap gap-2 pt-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Dokumente suchen..."
              value={searchQuery}
              onChange={(e) => onSearch?.(e.target.value)}
              className="pl-8"
            />
          </div>
          <Select
            value={selectedType}
            onValueChange={(v) => onTypeFilter?.(v as PrivatDocumentType | 'all')}
          >
            <SelectTrigger className="w-[180px]">
              <Filter className="mr-2 h-4 w-4" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DOCUMENT_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="mb-2">Keine Dokumente gefunden</p>
            {onCreate && (
              <Button variant="outline" onClick={onCreate}>
                <Plus className="mr-2 h-4 w-4" />
                Erstes Dokument hochladen
              </Button>
            )}
          </div>
        ) : viewMode === 'list' ? (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titel</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Größe</TableHead>
                  <TableHead>Erstellt</TableHead>
                  <TableHead className="w-[50px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    document={doc}
                    onSelect={onSelect}
                    onEdit={onEdit}
                    onDownload={onDownload}
                    onDelete={onDelete}
                  />
                ))}
              </TableBody>
            </Table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-4">
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
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {documents.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onSelect={onSelect}
                onEdit={onEdit}
                onDownload={onDownload}
                onDelete={onDelete}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface DocumentRowProps {
  document: PrivatDocument;
  onSelect?: (doc: PrivatDocument) => void;
  onEdit?: (doc: PrivatDocument) => void;
  onDownload?: (doc: PrivatDocument) => void;
  onDelete?: (doc: PrivatDocument) => void;
}

function DocumentRow({
  document,
  onSelect,
  onEdit,
  onDownload,
  onDelete,
}: DocumentRowProps) {
  return (
    <TableRow
      className={onSelect ? 'cursor-pointer hover:bg-muted/50' : undefined}
      onClick={() => onSelect?.(document)}
    >
      <TableCell>
        <div className="flex items-center gap-2">
          {document.isExtraEncrypted ? (
            <Lock className="h-4 w-4 text-amber-500" />
          ) : (
            <File className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="font-medium">{document.title}</span>
        </div>
      </TableCell>
      <TableCell>
        <Badge variant="secondary" className={getTypeColor(document.documentType)}>
          {getTypeLabel(document.documentType)}
        </Badge>
      </TableCell>
      <TableCell className="text-muted-foreground">
        {formatBytes(document.fileSize)}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {formatDate(document.createdAt)}
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
            <DropdownMenuItem onClick={() => onSelect?.(document)}>
              <Eye className="mr-2 h-4 w-4" />
              Anzeigen
            </DropdownMenuItem>
            {onDownload && (
              <DropdownMenuItem onClick={() => onDownload(document)}>
                <Download className="mr-2 h-4 w-4" />
                Herunterladen
              </DropdownMenuItem>
            )}
            {onEdit && (
              <DropdownMenuItem onClick={() => onEdit(document)}>
                <Edit className="mr-2 h-4 w-4" />
                Bearbeiten
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            {onDelete && (
              <DropdownMenuItem
                onClick={() => onDelete(document)}
                className="text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Löschen
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  );
}

function DocumentCard({
  document,
  onSelect,
  onEdit,
  onDownload,
  onDelete,
}: DocumentRowProps) {
  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow',
        onSelect && 'cursor-pointer'
      )}
      onClick={() => onSelect?.(document)}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            {document.isExtraEncrypted ? (
              <Lock className="h-5 w-5 text-amber-500" />
            ) : (
              <File className="h-5 w-5 text-muted-foreground" />
            )}
            <Badge variant="secondary" className={getTypeColor(document.documentType)}>
              {getTypeLabel(document.documentType)}
            </Badge>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onSelect?.(document)}>
                <Eye className="mr-2 h-4 w-4" />
                Anzeigen
              </DropdownMenuItem>
              {onDownload && (
                <DropdownMenuItem onClick={() => onDownload(document)}>
                  <Download className="mr-2 h-4 w-4" />
                  Herunterladen
                </DropdownMenuItem>
              )}
              {onEdit && (
                <DropdownMenuItem onClick={() => onEdit(document)}>
                  <Edit className="mr-2 h-4 w-4" />
                  Bearbeiten
                </DropdownMenuItem>
              )}
              {onDelete && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() => onDelete(document)}
                    className="text-destructive"
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Löschen
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <h4 className="font-medium truncate mb-2">{document.title}</h4>
        {document.description && (
          <p className="text-sm text-muted-foreground line-clamp-2 mb-2">
            {document.description}
          </p>
        )}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{formatBytes(document.fileSize)}</span>
          <span>{formatDate(document.createdAt)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export default PrivatDocumentList;
