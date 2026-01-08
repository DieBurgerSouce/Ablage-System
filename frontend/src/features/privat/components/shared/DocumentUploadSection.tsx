/**
 * DocumentUploadSection - Dokument-Upload-Sektion fuer Privat-Modul
 *
 * Wiederverwendbare Komponente zum Hochladen von Dokumenten
 * fuer Immobilien, Fahrzeuge, Versicherungen, Kredite und Geldanlagen.
 */

import * as React from 'react';
import { Upload, FileText, X, Loader2, Download, Trash2, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import * as privatApi from '../../api/privat-api';
import type { PrivatDocument, PrivatDocumentCreate, PrivatDocumentType } from '@/types/privat';

// Erlaubte Dateitypen
const ALLOWED_FILE_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/tiff',
  'image/webp',
];

const ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.webp'];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB

const DOCUMENT_TYPE_LABELS: Record<PrivatDocumentType, string> = {
  contract: 'Vertrag',
  invoice: 'Rechnung',
  receipt: 'Beleg',
  certificate: 'Zertifikat',
  insurance_policy: 'Versicherungspolice',
  tax_document: 'Steuerdokument',
  correspondence: 'Korrespondenz',
  photo: 'Foto',
  other: 'Sonstiges',
};

interface DocumentUploadSectionProps {
  spaceId: string;
  relatedEntityType: 'property' | 'vehicle' | 'insurance' | 'loan' | 'investment';
  relatedEntityId: string;
  title?: string;
  description?: string;
}

export function DocumentUploadSection({
  spaceId,
  relatedEntityType,
  relatedEntityId,
  title = 'Dokumente',
  description = 'Laden Sie zugehoerige Dokumente hoch',
}: DocumentUploadSectionProps) {
  const [documents, setDocuments] = React.useState<PrivatDocument[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [showUploadDialog, setShowUploadDialog] = React.useState(false);
  const [deleteDocument, setDeleteDocument] = React.useState<PrivatDocument | null>(null);

  // Upload form state
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [documentTitle, setDocumentTitle] = React.useState('');
  const [documentType, setDocumentType] = React.useState<PrivatDocumentType>('other');
  const [isDragging, setIsDragging] = React.useState(false);
  const [isUploading, setIsUploading] = React.useState(false);

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Load documents
  React.useEffect(() => {
    const loadDocuments = async () => {
      setIsLoading(true);
      try {
        const response = await privatApi.listDocuments(spaceId, {
          // In a real implementation, filter by related entity
          // For now, we load all and filter client-side
        });
        // Filter by related entity (this should be done server-side ideally)
        setDocuments(response.items);
      } catch (err) {
        console.error('Fehler beim Laden der Dokumente:', err);
      } finally {
        setIsLoading(false);
      }
    };
    loadDocuments();
  }, [spaceId, relatedEntityType, relatedEntityId]);

  const validateFile = (file: File): string | null => {
    if (!ALLOWED_FILE_TYPES.includes(file.type)) {
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (!ext || !ALLOWED_EXTENSIONS.some((e) => e === `.${ext}`)) {
        return `Dateityp nicht erlaubt. Erlaubte Typen: ${ALLOWED_EXTENSIONS.join(', ')}`;
      }
    }

    if (file.size > MAX_FILE_SIZE) {
      return `Datei zu gross. Maximum: ${MAX_FILE_SIZE / 1024 / 1024} MB`;
    }

    return null;
  };

  const handleFileSelect = React.useCallback((file: File) => {
    const error = validateFile(file);
    if (error) {
      toast.error(error);
      return;
    }
    setSelectedFile(file);
    // Set default title from filename
    if (!documentTitle) {
      const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '');
      setDocumentTitle(nameWithoutExt);
    }
  }, [documentTitle]);

  const handleDrop = React.useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);

      const file = e.dataTransfer.files[0];
      if (file) {
        handleFileSelect(file);
      }
    },
    [handleFileSelect]
  );

  const handleDragOver = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = React.useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const removeFile = () => {
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || !documentTitle.trim()) {
      toast.error('Bitte Titel und Datei angeben');
      return;
    }

    setIsUploading(true);
    try {
      const data: PrivatDocumentCreate = {
        title: documentTitle.trim(),
        documentType,
        fileSize: selectedFile.size,
        mimeType: selectedFile.type,
      };

      const newDoc = await privatApi.createDocument(spaceId, data);
      setDocuments((prev) => [newDoc, ...prev]);

      toast.success('Dokument hochgeladen');
      resetUploadForm();
      setShowUploadDialog(false);
    } catch (err) {
      toast.error('Fehler beim Hochladen');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteDocument) return;

    try {
      await privatApi.deleteDocument(deleteDocument.id);
      setDocuments((prev) => prev.filter((d) => d.id !== deleteDocument.id));
      toast.success('Dokument geloescht');
    } catch (err) {
      toast.error('Fehler beim Loeschen');
    } finally {
      setDeleteDocument(null);
    }
  };

  const resetUploadForm = () => {
    setSelectedFile(null);
    setDocumentTitle('');
    setDocumentType('other');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDownload = async (doc: PrivatDocument) => {
    try {
      await privatApi.downloadAndSaveDocument(doc.id, doc.title);
    } catch (err) {
      toast.error('Fehler beim Download');
    }
  };

  const formatFileSize = (bytes: number | undefined): string => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <Button onClick={() => setShowUploadDialog(true)}>
            <Upload className="mr-2 h-4 w-4" />
            Hochladen
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <FileText className="h-12 w-12 mx-auto mb-3 opacity-50" />
            <p>Keine Dokumente vorhanden</p>
            <p className="text-sm">Laden Sie Ihr erstes Dokument hoch</p>
          </div>
        ) : (
          <div className="space-y-2">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="p-2 bg-muted rounded-lg shrink-0">
                    <FileText className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium truncate">{doc.title}</p>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <span>{DOCUMENT_TYPE_LABELS[doc.documentType]}</span>
                      <span>•</span>
                      <span>{formatFileSize(doc.fileSize)}</span>
                      <span>•</span>
                      <span>{new Date(doc.createdAt).toLocaleDateString('de-DE')}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => window.open(privatApi.getDocumentDownloadUrl(doc.id), '_blank')}
                    title="Vorschau"
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDownload(doc)}
                    title="Herunterladen"
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setDeleteDocument(doc)}
                    title="Loeschen"
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {/* Upload Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={(open) => {
        if (!open) resetUploadForm();
        setShowUploadDialog(open);
      }}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Dokument hochladen</DialogTitle>
            <DialogDescription>
              Laden Sie ein Dokument hoch und versehen Sie es mit einem Titel.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Dropzone */}
            <div
              className={`relative border-2 border-dashed rounded-lg p-6 transition-colors cursor-pointer ${
                isDragging
                  ? 'border-primary bg-primary/5'
                  : selectedFile
                    ? 'border-green-500 bg-green-50 dark:bg-green-950/20'
                    : 'border-muted-foreground/25 hover:border-muted-foreground/50'
              }`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={ALLOWED_EXTENSIONS.join(',')}
                onChange={handleFileInputChange}
                className="hidden"
              />

              {selectedFile ? (
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-green-100 dark:bg-green-900 rounded-lg">
                    <FileText className="w-8 h-8 text-green-600 dark:text-green-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{selectedFile.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {formatFileSize(selectedFile.size)}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile();
                    }}
                    className="shrink-0"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              ) : (
                <div className="text-center">
                  <Upload className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                  <p className="font-medium">Datei hierher ziehen oder klicken</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    PDF, PNG, JPG, TIFF (max. 50 MB)
                  </p>
                </div>
              )}
            </div>

            {/* Title */}
            <div className="space-y-2">
              <Label htmlFor="title">Titel</Label>
              <Input
                id="title"
                value={documentTitle}
                onChange={(e) => setDocumentTitle(e.target.value)}
                placeholder="z.B. Kaufvertrag 2024"
                maxLength={100}
              />
            </div>

            {/* Document Type */}
            <div className="space-y-2">
              <Label>Dokumenttyp</Label>
              <Select
                value={documentType}
                onValueChange={(value) => setDocumentType(value as PrivatDocumentType)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Typ auswaehlen" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(DOCUMENT_TYPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                resetUploadForm();
                setShowUploadDialog(false);
              }}
            >
              Abbrechen
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!selectedFile || !documentTitle.trim() || isUploading}
            >
              {isUploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isUploading ? 'Hochladen...' : 'Hochladen'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteDocument} onOpenChange={(open) => !open && setDeleteDocument(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Dokument loeschen</AlertDialogTitle>
            <AlertDialogDescription>
              Moechten Sie das Dokument "{deleteDocument?.title}" wirklich loeschen?
              Diese Aktion kann nicht rueckgaengig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Loeschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

export default DocumentUploadSection;
