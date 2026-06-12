/**
 * Portal Documents Route
 *
 * Kundenportal Dokumenten-Verwaltung mit Upload.
 */

import { createFileRoute } from '@tanstack/react-router';
import { useState, useRef } from 'react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import { Upload, FileText, File, Download, Loader2, CheckCircle, Clock, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useToast } from '@/components/ui/use-toast';
import {
  usePortalDocuments,
  usePortalUploadDocument,
  usePortalAllowedFileTypes,
} from '@/features/portal';
import type { DocumentProcessingStatus } from '@/features/portal';

export const Route = createFileRoute('/portal/documents')({
  component: DocumentsPage,
});

const statusLabels: Record<DocumentProcessingStatus, string> = {
  pending: 'Ausstehend',
  processing: 'In Bearbeitung',
  completed: 'Verarbeitet',
  failed: 'Fehlgeschlagen',
};

const statusIcons: Record<DocumentProcessingStatus, React.ReactNode> = {
  pending: <Clock className="h-4 w-4 text-yellow-500" />,
  processing: <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />,
  completed: <CheckCircle className="h-4 w-4 text-green-500" />,
  failed: <XCircle className="h-4 w-4 text-red-500" />,
};

function DocumentsPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const { toast } = useToast();
  const { data: documents, isLoading } = usePortalDocuments({});
  const { data: allowedTypes } = usePortalAllowedFileTypes();
  const uploadDocument = usePortalUploadDocument();

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];

    // Validate file type
    if (allowedTypes?.types && !allowedTypes.types.some(type =>
      file.type === type || file.name.toLowerCase().endsWith(type.replace('*', ''))
    )) {
      toast({
        title: 'Dateityp nicht erlaubt',
        description: `Erlaubte Typen: ${allowedTypes.types.join(', ')}`,
        variant: 'destructive',
      });
      return;
    }

    // Validate file size
    if (allowedTypes?.max_file_size && file.size > allowedTypes.max_file_size) {
      toast({
        title: 'Datei zu gross',
        description: `Maximale Größe: ${allowedTypes.max_file_size_mb} MB`,
        variant: 'destructive',
      });
      return;
    }

    setUploading(true);
    try {
      await uploadDocument.mutateAsync({
        file,
        description: file.name,
      });
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const formatFileSize = (bytes: number | null): string => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dokumente</h1>
          <p className="text-muted-foreground mt-1">
            Laden Sie Dokumente hoch oder sehen Sie Ihre hochgeladenen Dateien
          </p>
        </div>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept={allowedTypes?.types?.join(',') || '.pdf,.jpg,.jpeg,.png'}
            onChange={handleFileChange}
          />
          <Button onClick={handleUploadClick} disabled={uploading}>
            {uploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Wird hochgeladen...
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                Dokument hochladen
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Upload Info */}
      {allowedTypes && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-col sm:flex-row gap-4 text-sm text-muted-foreground">
              <div>
                <strong>Erlaubte Dateitypen:</strong> PDF, JPG, PNG
              </div>
              <div>
                <strong>Maximale Größe:</strong> {allowedTypes.max_file_size_mb || 10} MB
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Documents Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Hochgeladene Dokumente</CardTitle>
          <CardDescription>
            {documents?.total ?? 0} Dokumente
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : documents?.items && documents.items.length > 0 ? (
            <>
              {/* Desktop Table */}
              <div className="hidden md:block overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Dateiname</TableHead>
                      <TableHead>Typ</TableHead>
                      <TableHead>Größe</TableHead>
                      <TableHead>Hochgeladen</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Aktionen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.items.map((doc) => (
                      <TableRow key={doc.id}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <FileIcon mimeType={doc.mime_type} />
                            <span className="font-medium truncate max-w-[200px]">
                              {doc.original_filename}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {doc.document_type || '-'}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatFileSize(doc.file_size)}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {format(new Date(doc.created_at), 'dd.MM.yyyy HH:mm', { locale: de })}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            {statusIcons[doc.processing_status]}
                            <span className="text-sm">
                              {statusLabels[doc.processing_status]}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm">
                            <Download className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Mobile Cards */}
              <div className="md:hidden space-y-3">
                {documents.items.map((doc) => (
                  <div
                    key={doc.id}
                    className="p-4 rounded-lg border"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <FileIcon mimeType={doc.mime_type} />
                        <span className="font-medium truncate">
                          {doc.original_filename}
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        {statusIcons[doc.processing_status]}
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-2 text-sm text-muted-foreground">
                      <span>{formatFileSize(doc.file_size)}</span>
                      <span>
                        {format(new Date(doc.created_at), 'dd.MM.yyyy', { locale: de })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="mx-auto h-12 w-12 opacity-50 mb-3" />
              <p>Noch keine Dokumente hochgeladen.</p>
              <Button variant="outline" className="mt-4" onClick={handleUploadClick}>
                Erstes Dokument hochladen
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function FileIcon({ mimeType }: { mimeType: string | null }) {
  if (mimeType?.includes('pdf')) {
    return <File className="h-5 w-5 text-red-500" />;
  }
  if (mimeType?.includes('image')) {
    return <File className="h-5 w-5 text-green-500" />;
  }
  return <FileText className="h-5 w-5 text-gray-500" />;
}
