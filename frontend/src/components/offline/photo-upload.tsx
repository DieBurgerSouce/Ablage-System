/**
 * PhotoUpload Component
 *
 * Mobile-optimized photo capture and upload component.
 * Supports:
 * - Camera capture (mobile)
 * - File selection (desktop)
 * - Image preview and cropping
 * - Offline queuing
 * - Multiple photo selection
 */

import * as React from 'react';
import { Camera, Upload, X, RotateCw, Check, Image as ImageIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { addMutation } from '@/lib/storage/indexed-db';
import { apiClient } from '@/lib/api/client';
import { isOnline } from '@/lib/offline';
import { logger } from '@/lib/logger';

// ============================================
// Types
// ============================================

export interface PhotoUploadProps {
  /** Called when photos are uploaded or queued */
  onUpload?: (results: PhotoUploadResult[]) => void;
  /** Maximum number of photos (default: 10) */
  maxPhotos?: number;
  /** Maximum file size in bytes (default: 10MB) */
  maxFileSize?: number;
  /** Accepted file types */
  accept?: string;
  /** Upload endpoint */
  endpoint?: string;
  /** Additional metadata for upload */
  metadata?: Record<string, unknown>;
  /** Show preview dialog (default: true) */
  showPreview?: boolean;
  /** Custom className */
  className?: string;
  /** Disabled state */
  disabled?: boolean;
}

export interface PhotoUploadResult {
  file: File;
  success: boolean;
  queued: boolean;
  documentId?: string;
  error?: string;
}

interface PhotoPreview {
  file: File;
  dataUrl: string;
  rotation: number;
}

// ============================================
// Utility Functions
// ============================================

/**
 * Compress image to reduce file size
 */
async function compressImage(
  file: File,
  maxWidth = 1920,
  quality = 0.8
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    img.onload = () => {
      let width = img.width;
      let height = img.height;

      // Scale down if too large
      if (width > maxWidth) {
        height = (height * maxWidth) / width;
        width = maxWidth;
      }

      canvas.width = width;
      canvas.height = height;

      if (ctx) {
        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob(
          (blob) => {
            if (blob) {
              resolve(blob);
            } else {
              reject(new Error('Bildkomprimierung fehlgeschlagen'));
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
 * Rotate image canvas
 */
function rotateImage(dataUrl: string, degrees: number): Promise<string> {
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
        resolve(canvas.toDataURL('image/jpeg', 0.9));
      } else {
        reject(new Error('Canvas-Kontext nicht verfuegbar'));
      }
    };

    img.onerror = () => reject(new Error('Rotation fehlgeschlagen'));
    img.src = dataUrl;
  });
}

// ============================================
// Component
// ============================================

export function PhotoUpload({
  onUpload,
  maxPhotos = 10,
  maxFileSize = 10 * 1024 * 1024, // 10MB
  accept = 'image/*',
  endpoint = '/documents/upload',
  metadata = {},
  showPreview = true,
  className,
  disabled = false,
}: PhotoUploadProps) {
  const [previews, setPreviews] = React.useState<PhotoPreview[]>([]);
  const [isPreviewOpen, setIsPreviewOpen] = React.useState(false);
  const [isUploading, setIsUploading] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);

  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const cameraInputRef = React.useRef<HTMLInputElement>(null);

  /**
   * Handle file selection
   */
  const handleFileSelect = React.useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;

      setError(null);
      const newPreviews: PhotoPreview[] = [];

      for (let i = 0; i < Math.min(files.length, maxPhotos - previews.length); i++) {
        const file = files[i];

        // Validate file size
        if (file.size > maxFileSize) {
          setError(`Datei "${file.name}" ist zu gross (max. ${Math.round(maxFileSize / 1024 / 1024)}MB)`);
          continue;
        }

        // Validate file type
        if (!file.type.startsWith('image/')) {
          setError(`Datei "${file.name}" ist kein Bild`);
          continue;
        }

        // Create preview
        const dataUrl = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target?.result as string);
          reader.readAsDataURL(file);
        });

        newPreviews.push({
          file,
          dataUrl,
          rotation: 0,
        });
      }

      if (newPreviews.length > 0) {
        setPreviews((prev) => [...prev, ...newPreviews]);
        if (showPreview) {
          setIsPreviewOpen(true);
        } else {
          // Direct upload without preview
          await handleUpload([...previews, ...newPreviews]);
        }
      }
    },
    [maxPhotos, maxFileSize, previews, showPreview]
  );

  /**
   * Rotate a preview image
   */
  const handleRotate = React.useCallback(async (index: number) => {
    setPreviews((prev) => {
      const updated = [...prev];
      const item = updated[index];
      item.rotation = (item.rotation + 90) % 360;
      return updated;
    });
  }, []);

  /**
   * Remove a preview
   */
  const handleRemove = React.useCallback((index: number) => {
    setPreviews((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /**
   * Upload all photos
   */
  const handleUpload = React.useCallback(
    async (photosToUpload: PhotoPreview[] = previews) => {
      if (photosToUpload.length === 0) return;

      setIsUploading(true);
      setUploadProgress(0);
      setError(null);

      const results: PhotoUploadResult[] = [];
      const online = isOnline();

      for (let i = 0; i < photosToUpload.length; i++) {
        const preview = photosToUpload[i];
        setUploadProgress(((i + 1) / photosToUpload.length) * 100);

        try {
          // Apply rotation if needed
          let imageData = preview.dataUrl;
          if (preview.rotation !== 0) {
            imageData = await rotateImage(preview.dataUrl, preview.rotation);
          }

          // Compress image
          const blob = await compressImage(preview.file);
          const compressedFile = new File([blob], preview.file.name, {
            type: 'image/jpeg',
          });

          if (online) {
            // Online - upload directly
            const formData = new FormData();
            formData.append('file', compressedFile);
            Object.entries(metadata).forEach(([key, value]) => {
              formData.append(key, String(value));
            });

            const response = await apiClient.post(endpoint, formData, {
              headers: { 'Content-Type': 'multipart/form-data' },
              timeout: 60000, // 60s for uploads
            });

            results.push({
              file: preview.file,
              success: true,
              queued: false,
              documentId: response.data?.id,
            });

            logger.info('[PhotoUpload] Foto hochgeladen', {
              filename: preview.file.name,
              documentId: response.data?.id,
            });
          } else {
            // Offline - queue for later
            // Store base64 data for offline upload
            await addMutation({
              endpoint,
              method: 'POST',
              payload: {
                filename: preview.file.name,
                contentType: 'image/jpeg',
                base64Data: imageData.split(',')[1], // Remove data:image/jpeg;base64, prefix
                metadata,
              },
              maxRetries: 5,
            });

            results.push({
              file: preview.file,
              success: true,
              queued: true,
            });

            logger.info('[PhotoUpload] Foto in Queue gespeichert', {
              filename: preview.file.name,
            });
          }
        } catch (err) {
          const errorMessage = err instanceof Error ? err.message : 'Upload fehlgeschlagen';
          results.push({
            file: preview.file,
            success: false,
            queued: false,
            error: errorMessage,
          });

          logger.error('[PhotoUpload] Upload fehlgeschlagen', {
            filename: preview.file.name,
            error: errorMessage,
          });
        }
      }

      setIsUploading(false);
      setPreviews([]);
      setIsPreviewOpen(false);
      onUpload?.(results);

      // Show summary
      const succeeded = results.filter((r) => r.success && !r.queued).length;
      const queued = results.filter((r) => r.queued).length;
      const failed = results.filter((r) => !r.success).length;

      if (failed > 0) {
        setError(`${failed} von ${results.length} Uploads fehlgeschlagen`);
      }
    },
    [previews, endpoint, metadata, onUpload]
  );

  /**
   * Trigger camera input
   */
  const openCamera = React.useCallback(() => {
    cameraInputRef.current?.click();
  }, []);

  /**
   * Trigger file input
   */
  const openFileSelect = React.useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  return (
    <>
      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        multiple
        className="hidden"
        onChange={(e) => handleFileSelect(e.target.files)}
        disabled={disabled}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => handleFileSelect(e.target.files)}
        disabled={disabled}
      />

      {/* Upload buttons */}
      <div className={cn('flex gap-2', className)}>
        <Button
          variant="outline"
          onClick={openCamera}
          disabled={disabled || previews.length >= maxPhotos}
          className="flex-1"
        >
          <Camera className="mr-2 h-4 w-4" />
          Foto aufnehmen
        </Button>
        <Button
          variant="outline"
          onClick={openFileSelect}
          disabled={disabled || previews.length >= maxPhotos}
          className="flex-1"
        >
          <Upload className="mr-2 h-4 w-4" />
          Datei waehlen
        </Button>
      </div>

      {/* Error display */}
      {error && (
        <p className="text-sm text-destructive mt-2">{error}</p>
      )}

      {/* Preview dialog */}
      <Dialog open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Fotos ueberpruefen</DialogTitle>
            <DialogDescription>
              {previews.length} {previews.length === 1 ? 'Foto' : 'Fotos'} ausgewaehlt
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 py-4">
            {previews.map((preview, index) => (
              <Card key={index} className="relative overflow-hidden">
                <CardContent className="p-0">
                  <img
                    src={preview.dataUrl}
                    alt={`Vorschau ${index + 1}`}
                    className="w-full h-32 object-cover"
                    style={{
                      transform: `rotate(${preview.rotation}deg)`,
                    }}
                  />
                  <div className="absolute top-1 right-1 flex gap-1">
                    <Button
                      size="icon"
                      variant="secondary"
                      className="h-6 w-6"
                      onClick={() => handleRotate(index)}
                    >
                      <RotateCw className="h-3 w-3" />
                    </Button>
                    <Button
                      size="icon"
                      variant="destructive"
                      className="h-6 w-6"
                      onClick={() => handleRemove(index)}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                  <p className="text-xs truncate p-1 bg-muted">
                    {preview.file.name}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>

          {isUploading && (
            <div className="space-y-2">
              <Progress value={uploadProgress} />
              <p className="text-sm text-center text-muted-foreground">
                Hochladen... {Math.round(uploadProgress)}%
              </p>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsPreviewOpen(false)}
              disabled={isUploading}
            >
              Abbrechen
            </Button>
            <Button
              onClick={() => handleUpload()}
              disabled={isUploading || previews.length === 0}
            >
              <Check className="mr-2 h-4 w-4" />
              {isOnline() ? 'Hochladen' : 'Offline speichern'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default PhotoUpload;
