/**
 * Portal Upload Page
 *
 * Ermöglicht Lieferanten den direkten Upload von Rechnungen und Dokumenten.
 * Drag & Drop, Dokumenttyp-Auswahl, Referenznummer und Fortschrittsanzeige.
 */

import { useState, useCallback, useRef } from 'react';
import {
  Upload,
  FileText,
  File,
  CheckCircle,
  Loader2,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import {
  usePortalUploadDocument,
  usePortalAllowedFileTypes,
} from '../hooks/use-portal-queries';

const DOCUMENT_TYPES = [
  { value: 'rechnung', label: 'Rechnung' },
  { value: 'gutschrift', label: 'Gutschrift' },
  { value: 'lieferschein', label: 'Lieferschein' },
] as const;

interface UploadResult {
  documentId: string;
  filename: string;
}

export function PortalUploadPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState<string>('rechnung');
  const [referenceNumber, setReferenceNumber] = useState('');
  const [notes, setNotes] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);

  const { data: allowedTypes } = usePortalAllowedFileTypes();
  const uploadDocument = usePortalUploadDocument({
    onSuccess: (documentId) => {
      setUploadResult({
        documentId,
        filename: selectedFile?.name || '',
      });
      setUploadProgress(100);
    },
  });

  const isUploading = uploadDocument.isPending;

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      setSelectedFile(files[0]);
      setUploadResult(null);
      setUploadProgress(0);
    }
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setSelectedFile(files[0]);
      setUploadResult(null);
      setUploadProgress(0);
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setUploadResult(null);
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSubmit = async () => {
    if (!selectedFile) return;

    setUploadProgress(10);

    const progressInterval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + 10;
      });
    }, 200);

    try {
      await uploadDocument.mutateAsync({
        file: selectedFile,
        options: {
          document_type: documentType,
          description: [
            referenceNumber ? `Ref: ${referenceNumber}` : '',
            notes,
          ]
            .filter(Boolean)
            .join(' - ') || undefined,
        },
      });
    } finally {
      clearInterval(progressInterval);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setDocumentType('rechnung');
    setReferenceNumber('');
    setNotes('');
    setUploadResult(null);
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dokument hochladen</h1>
        <p className="text-muted-foreground mt-1">
          Laden Sie Rechnungen, Gutschriften oder Lieferscheine direkt hoch.
        </p>
      </div>

      {/* Upload Success */}
      {uploadResult && (
        <Card className="border-green-500/50 bg-green-50 dark:bg-green-950/20">
          <CardContent className="pt-6">
            <div className="flex items-center gap-4">
              <CheckCircle className="h-8 w-8 text-green-600" />
              <div>
                <p className="font-semibold text-green-800 dark:text-green-200">
                  Dokument erfolgreich hochgeladen
                </p>
                <p className="text-sm text-green-700 dark:text-green-300">
                  Datei: {uploadResult.filename}
                </p>
                <p className="text-sm text-green-700 dark:text-green-300">
                  Dokument-ID: {uploadResult.documentId}
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={handleReset}
            >
              Weiteres Dokument hochladen
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Upload Form */}
      {!uploadResult && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Datei auswählen</CardTitle>
            <CardDescription>
              Erlaubte Dateitypen: PDF, JPG, PNG.
              Maximale Größe: {allowedTypes?.max_file_size_mb || 10} MB.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Dropzone */}
            <div
              className={cn(
                'relative border-2 border-dashed rounded-lg p-8 transition-colors cursor-pointer',
                isDragOver
                  ? 'border-primary bg-primary/5'
                  : 'border-muted-foreground/25 hover:border-muted-foreground/50',
                selectedFile && 'border-primary/50 bg-primary/5'
              )}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => !selectedFile && fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept={allowedTypes?.types?.join(',') || '.pdf,.jpg,.jpeg,.png'}
                onChange={handleFileSelect}
              />

              {selectedFile ? (
                <div className="flex items-center gap-4">
                  <div className="p-3 rounded-lg bg-primary/10">
                    {selectedFile.type.includes('pdf') ? (
                      <File className="h-6 w-6 text-red-500" />
                    ) : (
                      <FileText className="h-6 w-6 text-blue-500" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{selectedFile.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {formatFileSize(selectedFile.size)}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveFile();
                    }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <div className="text-center">
                  <Upload className="mx-auto h-10 w-10 text-muted-foreground/50" />
                  <p className="mt-3 text-sm font-medium">
                    Datei hierher ziehen oder klicken zum Auswählen
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    PDF, JPG oder PNG bis {allowedTypes?.max_file_size_mb || 10} MB
                  </p>
                </div>
              )}
            </div>

            {/* Document Type */}
            <div className="space-y-2">
              <Label htmlFor="document-type">Dokumenttyp</Label>
              <Select value={documentType} onValueChange={setDocumentType}>
                <SelectTrigger id="document-type">
                  <SelectValue placeholder="Dokumenttyp wählen" />
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

            {/* Reference Number */}
            <div className="space-y-2">
              <Label htmlFor="reference-number">Referenznummer</Label>
              <Input
                id="reference-number"
                value={referenceNumber}
                onChange={(e) => setReferenceNumber(e.target.value)}
                placeholder="z.B. RE-2026-001234"
              />
            </div>

            {/* Notes */}
            <div className="space-y-2">
              <Label htmlFor="notes">Anmerkungen (optional)</Label>
              <Textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optionale Anmerkungen zum Dokument..."
                rows={3}
              />
            </div>

            {/* Upload Progress */}
            {isUploading && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Wird hochgeladen...</span>
                  <span className="font-medium">{uploadProgress}%</span>
                </div>
                <Progress value={uploadProgress} />
              </div>
            )}

            {/* Submit */}
            <Button
              className="w-full"
              size="lg"
              onClick={handleSubmit}
              disabled={!selectedFile || isUploading}
            >
              {isUploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Wird hochgeladen...
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  Hochladen
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default PortalUploadPage;
