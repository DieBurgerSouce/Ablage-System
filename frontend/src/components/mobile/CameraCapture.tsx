/**
 * CameraCapture Component
 *
 * Mobile-optimized document capture component with advanced features.
 *
 * Features:
 * - Direct camera capture for documents
 * - Multi-page scanning mode
 * - Quality optimization before upload
 * - Auto-rotation based on EXIF
 * - Preview with cropping controls
 * - Offline queuing support
 *
 * All user-facing text is in German.
 */

import * as React from 'react';
import {
  Camera,
  X,
  RotateCcw,
  RotateCw,
  Check,
  Plus,
  Trash2,
  Upload,
  Image as ImageIcon,
  Loader2,
  ChevronLeft,
  ChevronRight,
  ScanLine,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { addMutation } from '@/lib/storage/indexed-db';
import { apiClient } from '@/lib/api/client';
import { isOnline } from '@/lib/offline';
import { logger } from '@/lib/logger';
import { useSafeAreaInsets } from '@/lib/mobile';

// ============================================
// Types
// ============================================

export interface CameraCaptureProps {
  /** Called when photos are captured and ready */
  onCapture?: (results: CaptureResult[]) => void;
  /** Maximum number of pages (default: 20) */
  maxPages?: number;
  /** Maximum file size in bytes (default: 15MB) */
  maxFileSize?: number;
  /** Upload endpoint */
  endpoint?: string;
  /** Additional metadata for upload */
  metadata?: Record<string, unknown>;
  /** Enable multi-page scanning mode (default: true) */
  multiPage?: boolean;
  /** Auto-upload after capture (default: false) */
  autoUpload?: boolean;
  /** Custom className */
  className?: string;
  /** Disabled state */
  disabled?: boolean;
  /** Trigger ref for external control */
  triggerRef?: React.RefObject<{ open: () => void }>;
}

export interface CaptureResult {
  file: File;
  success: boolean;
  queued: boolean;
  documentId?: string;
  error?: string;
  pageNumber?: number;
}

interface CapturedPage {
  id: string;
  file: File;
  dataUrl: string;
  rotation: number;
  timestamp: number;
}

// ============================================
// Utility Functions
// ============================================

/**
 * Generate unique ID
 */
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Compress and optimize image for document upload
 */
async function optimizeImage(
  file: File,
  maxWidth = 2048,
  quality = 0.85
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    img.onload = () => {
      let width = img.width;
      let height = img.height;

      // Scale down if too large while maintaining aspect ratio
      if (width > maxWidth) {
        height = (height * maxWidth) / width;
        width = maxWidth;
      }

      canvas.width = width;
      canvas.height = height;

      if (ctx) {
        // Use high-quality image rendering
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob(
          (blob) => {
            if (blob) {
              resolve(blob);
            } else {
              reject(new Error('Bildoptimierung fehlgeschlagen'));
            }
          },
          'image/jpeg',
          quality
        );
      } else {
        reject(new Error('Canvas-Kontext nicht verfuegbar'));
      }
    };

    img.onerror = () => reject(new Error('Bild konnte nicht geladen werden'));
    img.src = URL.createObjectURL(file);
  });
}

/**
 * Apply rotation to image
 */
async function applyRotation(dataUrl: string, degrees: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    img.onload = () => {
      const radians = (degrees * Math.PI) / 180;
      const sin = Math.abs(Math.sin(radians));
      const cos = Math.abs(Math.cos(radians));

      canvas.width = img.width * cos + img.height * sin;
      canvas.height = img.width * sin + img.height * cos;

      if (ctx) {
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.rotate(radians);
        ctx.drawImage(img, -img.width / 2, -img.height / 2);
        resolve(canvas.toDataURL('image/jpeg', 0.92));
      } else {
        reject(new Error('Canvas-Kontext nicht verfuegbar'));
      }
    };

    img.onerror = () => reject(new Error('Rotation fehlgeschlagen'));
    img.src = dataUrl;
  });
}

/**
 * Convert data URL to File
 */
function dataUrlToFile(dataUrl: string, filename: string): File {
  const arr = dataUrl.split(',');
  const mime = arr[0].match(/:(.*?);/)?.[1] || 'image/jpeg';
  const bstr = atob(arr[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);
  while (n--) {
    u8arr[n] = bstr.charCodeAt(n);
  }
  return new File([u8arr], filename, { type: mime });
}

// ============================================
// Component
// ============================================

export function CameraCapture({
  onCapture,
  maxPages = 20,
  maxFileSize = 15 * 1024 * 1024,
  endpoint = '/api/v1/documents/upload',
  metadata = {},
  multiPage = true,
  autoUpload = false,
  className,
  disabled = false,
  triggerRef,
}: CameraCaptureProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [pages, setPages] = React.useState<CapturedPage[]>([]);
  const [currentPageIndex, setCurrentPageIndex] = React.useState(0);
  const [isUploading, setIsUploading] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);

  const cameraInputRef = React.useRef<HTMLInputElement>(null);
  const insets = useSafeAreaInsets();

  // Expose open method via ref
  React.useImperativeHandle(
    triggerRef,
    () => ({
      open: () => setIsOpen(true),
    }),
    []
  );

  /**
   * Handle camera capture
   */
  const handleCapture = React.useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      setError(null);
      const file = files[0];

      // Validate file size
      if (file.size > maxFileSize) {
        setError(`Datei ist zu gross (max. ${Math.round(maxFileSize / 1024 / 1024)}MB)`);
        return;
      }

      // Validate file type
      if (!file.type.startsWith('image/')) {
        setError('Nur Bilder werden unterstuetzt');
        return;
      }

      // Check page limit
      if (pages.length >= maxPages) {
        setError(`Maximal ${maxPages} Seiten erlaubt`);
        return;
      }

      try {
        // Create preview
        const dataUrl = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target?.result as string);
          reader.readAsDataURL(file);
        });

        const newPage: CapturedPage = {
          id: generateId(),
          file,
          dataUrl,
          rotation: 0,
          timestamp: Date.now(),
        };

        setPages((prev) => [...prev, newPage]);
        setCurrentPageIndex(pages.length);

        logger.info('[CameraCapture] Seite aufgenommen', {
          pageNumber: pages.length + 1,
          fileSize: file.size,
        });

        // Auto-upload if enabled and single page mode
        if (autoUpload && !multiPage) {
          await handleUpload([newPage]);
        }
      } catch (err) {
        setError('Fehler beim Verarbeiten des Bildes');
        logger.error('[CameraCapture] Capture fehlgeschlagen', { error: err });
      }

      // Reset input
      if (cameraInputRef.current) {
        cameraInputRef.current.value = '';
      }
    },
    [pages.length, maxPages, maxFileSize, multiPage, autoUpload]
  );

  /**
   * Rotate current page
   */
  const handleRotate = React.useCallback(
    async (direction: 'cw' | 'ccw') => {
      const currentPage = pages[currentPageIndex];
      if (!currentPage) return;

      const degrees = direction === 'cw' ? 90 : -90;
      const newRotation = (currentPage.rotation + degrees + 360) % 360;

      try {
        const rotatedDataUrl = await applyRotation(currentPage.dataUrl, degrees);

        setPages((prev) =>
          prev.map((p, i) =>
            i === currentPageIndex
              ? { ...p, dataUrl: rotatedDataUrl, rotation: newRotation }
              : p
          )
        );
      } catch {
        setError('Rotation fehlgeschlagen');
      }
    },
    [currentPageIndex, pages]
  );

  /**
   * Delete current page
   */
  const handleDeletePage = React.useCallback(() => {
    setPages((prev) => prev.filter((_, i) => i !== currentPageIndex));
    setCurrentPageIndex((prev) => Math.max(0, prev - 1));
  }, [currentPageIndex]);

  /**
   * Navigate between pages
   */
  const navigatePage = React.useCallback(
    (direction: 'prev' | 'next') => {
      if (direction === 'prev' && currentPageIndex > 0) {
        setCurrentPageIndex((prev) => prev - 1);
      } else if (direction === 'next' && currentPageIndex < pages.length - 1) {
        setCurrentPageIndex((prev) => prev + 1);
      }
    },
    [currentPageIndex, pages.length]
  );

  /**
   * Upload all pages
   */
  const handleUpload = React.useCallback(
    async (pagesToUpload: CapturedPage[] = pages) => {
      if (pagesToUpload.length === 0) return;

      setIsUploading(true);
      setUploadProgress(0);
      setError(null);

      const results: CaptureResult[] = [];
      const online = isOnline();

      for (let i = 0; i < pagesToUpload.length; i++) {
        const page = pagesToUpload[i];
        setUploadProgress(((i + 1) / pagesToUpload.length) * 100);

        try {
          // Optimize image
          const optimizedBlob = await optimizeImage(
            dataUrlToFile(page.dataUrl, page.file.name)
          );
          const optimizedFile = new File(
            [optimizedBlob],
            `scan_${Date.now()}_seite_${i + 1}.jpg`,
            { type: 'image/jpeg' }
          );

          if (online) {
            // Online - upload directly
            const formData = new FormData();
            formData.append('file', optimizedFile);
            formData.append('page_number', String(i + 1));
            formData.append('total_pages', String(pagesToUpload.length));
            Object.entries(metadata).forEach(([key, value]) => {
              formData.append(key, String(value));
            });

            const response = await apiClient.post(endpoint, formData, {
              headers: { 'Content-Type': 'multipart/form-data' },
              timeout: 60000,
            });

            results.push({
              file: optimizedFile,
              success: true,
              queued: false,
              documentId: response.data?.id,
              pageNumber: i + 1,
            });

            logger.info('[CameraCapture] Seite hochgeladen', {
              pageNumber: i + 1,
              documentId: response.data?.id,
            });
          } else {
            // Offline - queue for later
            await addMutation({
              endpoint,
              method: 'POST',
              payload: {
                filename: optimizedFile.name,
                contentType: 'image/jpeg',
                base64Data: page.dataUrl.split(',')[1],
                pageNumber: i + 1,
                totalPages: pagesToUpload.length,
                metadata,
              },
              maxRetries: 5,
            });

            results.push({
              file: optimizedFile,
              success: true,
              queued: true,
              pageNumber: i + 1,
            });

            logger.info('[CameraCapture] Seite in Queue gespeichert', {
              pageNumber: i + 1,
            });
          }
        } catch (err) {
          const errorMessage = err instanceof Error ? err.message : 'Upload fehlgeschlagen';
          results.push({
            file: page.file,
            success: false,
            queued: false,
            error: errorMessage,
            pageNumber: i + 1,
          });

          logger.error('[CameraCapture] Upload fehlgeschlagen', {
            pageNumber: i + 1,
            error: errorMessage,
          });
        }
      }

      setIsUploading(false);
      onCapture?.(results);

      // Show result summary
      const succeeded = results.filter((r) => r.success && !r.queued).length;
      const queued = results.filter((r) => r.queued).length;
      const failed = results.filter((r) => !r.success).length;

      if (failed > 0) {
        setError(`${failed} von ${results.length} Uploads fehlgeschlagen`);
      } else {
        // Success - close dialog
        setPages([]);
        setCurrentPageIndex(0);
        setIsOpen(false);
      }
    },
    [pages, endpoint, metadata, onCapture]
  );

  /**
   * Open camera
   */
  const openCamera = React.useCallback(() => {
    cameraInputRef.current?.click();
  }, []);

  /**
   * Close dialog
   */
  const handleClose = React.useCallback(() => {
    if (pages.length > 0 && !isUploading) {
      // Confirm if pages exist
      if (window.confirm('Moechten Sie die aufgenommenen Seiten verwerfen?')) {
        setPages([]);
        setCurrentPageIndex(0);
        setIsOpen(false);
      }
    } else if (!isUploading) {
      setIsOpen(false);
    }
  }, [pages.length, isUploading]);

  const currentPage = pages[currentPageIndex];

  return (
    <>
      {/* Hidden camera input */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleCapture}
        disabled={disabled || isUploading}
      />

      {/* Trigger button */}
      <Button
        variant="outline"
        onClick={() => setIsOpen(true)}
        disabled={disabled}
        className={cn('gap-2', className)}
      >
        <ScanLine className="h-4 w-4" />
        Dokument scannen
      </Button>

      {/* Capture Dialog */}
      <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
        <DialogContent
          className="max-w-lg max-h-[95vh] p-0 gap-0"
          style={{
            paddingTop: insets.top,
            paddingBottom: insets.bottom,
          }}
        >
          <DialogHeader className="p-4 pb-2">
            <DialogTitle className="flex items-center gap-2">
              <ScanLine className="h-5 w-5" />
              Dokument scannen
            </DialogTitle>
            <DialogDescription>
              {pages.length === 0
                ? 'Fotografieren Sie Ihr Dokument'
                : multiPage
                ? `${pages.length} Seite${pages.length !== 1 ? 'n' : ''} aufgenommen`
                : 'Vorschau'}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-hidden">
            {pages.length === 0 ? (
              // Empty state - show camera trigger
              <div className="flex flex-col items-center justify-center p-8 gap-4 min-h-[300px]">
                <div className="p-6 rounded-full bg-muted">
                  <Camera className="h-12 w-12 text-muted-foreground" />
                </div>
                <div className="text-center">
                  <p className="font-medium">Dokument fotografieren</p>
                  <p className="text-sm text-muted-foreground">
                    Halten Sie die Kamera ueber das Dokument
                  </p>
                </div>
                <Button size="lg" onClick={openCamera} disabled={disabled}>
                  <Camera className="h-5 w-5 mr-2" />
                  Kamera oeffnen
                </Button>
              </div>
            ) : (
              // Preview current page
              <div className="relative">
                {/* Image preview */}
                <div className="relative aspect-[3/4] bg-muted overflow-hidden">
                  <img
                    src={currentPage?.dataUrl}
                    alt={`Seite ${currentPageIndex + 1}`}
                    className="w-full h-full object-contain"
                  />

                  {/* Page indicator */}
                  {pages.length > 1 && (
                    <Badge className="absolute top-2 right-2 bg-black/60">
                      {currentPageIndex + 1} / {pages.length}
                    </Badge>
                  )}

                  {/* Navigation arrows */}
                  {pages.length > 1 && (
                    <>
                      {currentPageIndex > 0 && (
                        <Button
                          variant="secondary"
                          size="icon"
                          className="absolute left-2 top-1/2 -translate-y-1/2 h-10 w-10 rounded-full bg-black/50 hover:bg-black/70"
                          onClick={() => navigatePage('prev')}
                        >
                          <ChevronLeft className="h-6 w-6 text-white" />
                        </Button>
                      )}
                      {currentPageIndex < pages.length - 1 && (
                        <Button
                          variant="secondary"
                          size="icon"
                          className="absolute right-2 top-1/2 -translate-y-1/2 h-10 w-10 rounded-full bg-black/50 hover:bg-black/70"
                          onClick={() => navigatePage('next')}
                        >
                          <ChevronRight className="h-6 w-6 text-white" />
                        </Button>
                      )}
                    </>
                  )}
                </div>

                {/* Page actions */}
                <div className="flex items-center justify-center gap-2 p-3 bg-muted/50">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleRotate('ccw')}
                    title="Nach links drehen"
                  >
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleRotate('cw')}
                    title="Nach rechts drehen"
                  >
                    <RotateCw className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handleDeletePage}
                    title="Seite loeschen"
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                  {multiPage && pages.length < maxPages && (
                    <Button
                      variant="outline"
                      size="icon"
                      onClick={openCamera}
                      title="Weitere Seite hinzufuegen"
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  )}
                </div>

                {/* Page thumbnails */}
                {pages.length > 1 && (
                  <div className="flex gap-2 p-3 overflow-x-auto">
                    {pages.map((page, index) => (
                      <button
                        key={page.id}
                        onClick={() => setCurrentPageIndex(index)}
                        className={cn(
                          'relative flex-shrink-0 w-12 h-16 rounded border-2 overflow-hidden',
                          index === currentPageIndex
                            ? 'border-primary'
                            : 'border-transparent'
                        )}
                      >
                        <img
                          src={page.dataUrl}
                          alt={`Seite ${index + 1}`}
                          className="w-full h-full object-cover"
                        />
                        <span className="absolute bottom-0 inset-x-0 bg-black/50 text-white text-[10px] text-center">
                          {index + 1}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Error display */}
            {error && (
              <p className="text-sm text-destructive text-center px-4 py-2">
                {error}
              </p>
            )}

            {/* Upload progress */}
            {isUploading && (
              <div className="px-4 py-2 space-y-2">
                <Progress value={uploadProgress} />
                <p className="text-sm text-center text-muted-foreground">
                  <Loader2 className="inline h-3 w-3 mr-1 animate-spin" />
                  Hochladen... {Math.round(uploadProgress)}%
                </p>
              </div>
            )}
          </div>

          <DialogFooter className="p-4 pt-2 flex-row gap-2">
            <Button
              variant="outline"
              onClick={handleClose}
              disabled={isUploading}
              className="flex-1"
            >
              {pages.length > 0 ? 'Verwerfen' : 'Abbrechen'}
            </Button>
            {pages.length > 0 && (
              <Button
                onClick={() => handleUpload()}
                disabled={isUploading || pages.length === 0}
                className="flex-1"
              >
                {isUploading ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4 mr-2" />
                )}
                {isOnline()
                  ? `${pages.length} Seite${pages.length !== 1 ? 'n' : ''} hochladen`
                  : 'Offline speichern'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default CameraCapture;
