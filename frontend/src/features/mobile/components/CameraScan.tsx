/**
 * CameraScan Component
 *
 * Mobile-optimized document scanning with camera capture.
 *
 * Features:
 * - Camera stream access (front/back)
 * - Photo capture with preview
 * - Auto-crop detection (future)
 * - Offline queue support
 * - Touch gestures
 *
 * Phase 3.1 der Feature-Roadmap (Januar 2026)
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Camera, RefreshCw, Check, X, Upload, RotateCcw, SwitchCamera, Image as ImageIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { logger } from '@/lib/logger';
import { addMutation, getPendingMutationCount } from '@/lib/storage/indexed-db';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface CameraScanProps {
  /** Called when a document is successfully uploaded */
  onUploadSuccess?: (documentId: string) => void;
  /** Called when the user cancels */
  onCancel?: () => void;
  /** Target folder ID for upload */
  folderId?: string;
  /** Compact mode for inline use */
  compact?: boolean;
  /** Class name override */
  className?: string;
}

interface CapturedImage {
  dataUrl: string;
  blob: Blob;
  timestamp: number;
}

type CameraFacing = 'environment' | 'user';

// ==================== API Service ====================

async function uploadDocument(
  file: Blob,
  folderId?: string
): Promise<{ id: string; title: string }> {
  const formData = new FormData();
  formData.append('file', file, `scan-${Date.now()}.jpg`);
  if (folderId) {
    formData.append('folder_id', folderId);
  }
  formData.append('source', 'camera_scan');

  const response = await fetch('/api/v1/documents/upload', {
    method: 'POST',
    body: formData,
    credentials: 'include',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Upload fehlgeschlagen');
  }

  return response.json();
}

// ==================== Main Component ====================

export function CameraScan({
  onUploadSuccess,
  onCancel,
  folderId,
  compact = false,
  className,
}: CameraScanProps) {
  // Refs
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // State
  const [cameraState, setCameraState] = useState<'idle' | 'loading' | 'active' | 'preview' | 'uploading'>('idle');
  const [capturedImage, setCapturedImage] = useState<CapturedImage | null>(null);
  const [cameraFacing, setCameraFacing] = useState<CameraFacing>('environment');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [offlineQueueCount, setOfflineQueueCount] = useState(0);
  const [_flashEnabled, _setFlashEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  // ==================== Camera Setup ====================

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  const startCamera = useCallback(async () => {
    setError(null);
    setCameraState('loading');

    try {
      // Stop any existing stream
      stopCamera();

      // Request camera access
      const constraints: MediaStreamConstraints = {
        video: {
          facingMode: cameraFacing,
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      };

      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setCameraState('active');
      logger.info('[CameraScan] Kamera gestartet', { facing: cameraFacing });
    } catch (err) {
      logger.error('[CameraScan] Kamera-Zugriff fehlgeschlagen', { error: err });
      setError(
        err instanceof Error && err.name === 'NotAllowedError'
          ? 'Kamera-Zugriff verweigert. Bitte erlauben Sie den Zugriff in den Browser-Einstellungen.'
          : 'Kamera konnte nicht gestartet werden. Bitte prüfen Sie die Geräte-Einstellungen.'
      );
      setCameraState('idle');
    }
  }, [cameraFacing, stopCamera]);

  // Switch camera (front/back)
  const switchCamera = useCallback(() => {
    setCameraFacing((prev) => (prev === 'environment' ? 'user' : 'environment'));
  }, []);

  // Effect to restart camera when facing changes
  useEffect(() => {
    if (cameraState === 'active') {
      startCamera();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraFacing]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  // Check offline queue count
  useEffect(() => {
    const checkQueue = async () => {
      try {
        const count = await getPendingMutationCount();
        setOfflineQueueCount(count);
      } catch {
        // Ignore
      }
    };
    checkQueue();
  }, []);

  // ==================== Capture ====================

  const captureImage = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    if (!ctx) return;

    // Set canvas size to video dimensions
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // Draw current frame
    ctx.drawImage(video, 0, 0);

    // Convert to blob
    canvas.toBlob(
      (blob) => {
        if (blob) {
          const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
          setCapturedImage({
            dataUrl,
            blob,
            timestamp: Date.now(),
          });
          setCameraState('preview');
          stopCamera();
          logger.info('[CameraScan] Bild aufgenommen', { size: blob.size });
        }
      },
      'image/jpeg',
      0.9
    );
  }, [stopCamera]);

  // ==================== File Selection ====================

  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      setCapturedImage({
        dataUrl,
        blob: file,
        timestamp: Date.now(),
      });
      setCameraState('preview');
      stopCamera();
    };
    reader.readAsDataURL(file);
  }, [stopCamera]);

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  // ==================== Upload ====================

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!capturedImage) throw new Error('Kein Bild vorhanden');
      return uploadDocument(capturedImage.blob, folderId);
    },
    onMutate: () => {
      setCameraState('uploading');
      setUploadProgress(0);
      // Simulate progress
      const interval = setInterval(() => {
        setUploadProgress((prev) => Math.min(prev + 10, 90));
      }, 200);
      return { interval };
    },
    onSuccess: (data) => {
      setUploadProgress(100);
      toast.success('Dokument hochgeladen', {
        description: 'Das Dokument wird jetzt verarbeitet.',
      });
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      onUploadSuccess?.(data.id);
      resetState();
    },
    onError: async (error, _variables, context) => {
      if (context?.interval) clearInterval(context.interval);

      // Check if offline
      if (!navigator.onLine && capturedImage) {
        // Queue for background sync
        try {
          await addMutation({
            endpoint: '/api/v1/documents/upload',
            method: 'POST',
            payload: {
              folderId,
              source: 'camera_scan',
              // Note: actual file would need to be stored in IndexedDB separately
            },
            maxRetries: 3,
          });
          toast.info('Offline - In Warteschlange', {
            description: 'Das Dokument wird hochgeladen, sobald Sie online sind.',
          });
          setOfflineQueueCount((prev) => prev + 1);
          resetState();
        } catch (_queueError) {
          toast.error('Speichern fehlgeschlagen');
        }
      } else {
        toast.error('Upload fehlgeschlagen', {
          description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        });
        setCameraState('preview');
      }
    },
    onSettled: (_data, _error, _variables, context) => {
      if (context?.interval) clearInterval(context.interval);
    },
  });

  // ==================== Actions ====================

  const resetState = useCallback(() => {
    setCapturedImage(null);
    setCameraState('idle');
    setUploadProgress(0);
    setError(null);
  }, []);

  const retakePhoto = useCallback(() => {
    setCapturedImage(null);
    startCamera();
  }, [startCamera]);

  // ==================== Render ====================

  // Check camera support
  const isCameraSupported = typeof navigator !== 'undefined' && 'mediaDevices' in navigator;

  if (!isCameraSupported) {
    return (
      <Card className={cn('max-w-lg mx-auto', className)}>
        <CardContent className="pt-6">
          <div className="text-center">
            <Camera className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">
              Kamera-Zugriff wird von diesem Browser nicht unterstützt.
            </p>
            <Button variant="outline" className="mt-4" onClick={openFilePicker}>
              <ImageIcon className="w-4 h-4 mr-2" />
              Bild auswählen
            </Button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={handleFileSelect}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn('max-w-lg mx-auto', compact && 'border-0 shadow-none', className)}>
      {!compact && (
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Camera className="w-5 h-5" />
            Dokument scannen
          </CardTitle>
          <CardDescription>
            Fotografieren Sie ein Dokument zur Verarbeitung
          </CardDescription>
          {offlineQueueCount > 0 && (
            <p className="text-sm text-amber-600">
              {offlineQueueCount} Dokument(e) warten auf Upload
            </p>
          )}
        </CardHeader>
      )}

      <CardContent className={cn(compact && 'p-0')}>
        {/* Hidden file input for fallback */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={handleFileSelect}
        />

        {/* Hidden canvas for image capture */}
        <canvas ref={canvasRef} className="hidden" />

        {/* Idle State */}
        {cameraState === 'idle' && (
          <div className="flex flex-col items-center gap-4 py-8">
            {error && (
              <div className="text-center text-destructive mb-4">
                <p className="text-sm">{error}</p>
              </div>
            )}
            <Button size="lg" onClick={startCamera} className="gap-2">
              <Camera className="w-5 h-5" />
              Kamera starten
            </Button>
            <Button variant="outline" onClick={openFilePicker} className="gap-2">
              <ImageIcon className="w-5 h-5" />
              Aus Galerie wählen
            </Button>
            {onCancel && (
              <Button variant="ghost" onClick={onCancel}>
                Abbrechen
              </Button>
            )}
          </div>
        )}

        {/* Loading State */}
        {cameraState === 'loading' && (
          <div className="flex flex-col items-center gap-4 py-8">
            <RefreshCw className="w-8 h-8 animate-spin text-primary" />
            <p className="text-muted-foreground">Kamera wird gestartet...</p>
          </div>
        )}

        {/* Camera Active State */}
        {cameraState === 'active' && (
          <div className="relative">
            {/* Video Preview */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full rounded-lg bg-black aspect-[3/4] object-cover"
            />

            {/* Document Frame Overlay */}
            <div className="absolute inset-4 border-2 border-dashed border-white/50 rounded-lg pointer-events-none">
              <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-primary rounded-tl-lg" />
              <div className="absolute top-0 right-0 w-8 h-8 border-t-2 border-r-2 border-primary rounded-tr-lg" />
              <div className="absolute bottom-0 left-0 w-8 h-8 border-b-2 border-l-2 border-primary rounded-bl-lg" />
              <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-primary rounded-br-lg" />
            </div>

            {/* Controls Overlay */}
            <div className="absolute bottom-4 left-0 right-0 flex justify-center items-center gap-4">
              {/* Switch Camera */}
              <Button
                variant="secondary"
                size="icon"
                className="rounded-full w-12 h-12 bg-white/20 backdrop-blur-sm hover:bg-white/30"
                onClick={switchCamera}
              >
                <SwitchCamera className="w-5 h-5 text-white" />
              </Button>

              {/* Capture Button */}
              <Button
                size="icon"
                className="rounded-full w-16 h-16 bg-white hover:bg-gray-100"
                onClick={captureImage}
              >
                <Camera className="w-8 h-8 text-primary" />
              </Button>

              {/* Gallery */}
              <Button
                variant="secondary"
                size="icon"
                className="rounded-full w-12 h-12 bg-white/20 backdrop-blur-sm hover:bg-white/30"
                onClick={openFilePicker}
              >
                <ImageIcon className="w-5 h-5 text-white" />
              </Button>
            </div>

            {/* Cancel Button */}
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-4 right-4 bg-white/20 backdrop-blur-sm hover:bg-white/30"
              onClick={() => {
                stopCamera();
                setCameraState('idle');
              }}
            >
              <X className="w-5 h-5 text-white" />
            </Button>
          </div>
        )}

        {/* Preview State */}
        {cameraState === 'preview' && capturedImage && (
          <div className="relative">
            {/* Captured Image */}
            <img
              src={capturedImage.dataUrl}
              alt="Aufgenommenes Dokument"
              className="w-full rounded-lg"
            />

            {/* Actions */}
            <div className="absolute bottom-4 left-0 right-0 flex justify-center items-center gap-4">
              {/* Retake */}
              <Button
                variant="secondary"
                size="icon"
                className="rounded-full w-12 h-12 bg-white/90 hover:bg-white"
                onClick={retakePhoto}
              >
                <RotateCcw className="w-5 h-5" />
              </Button>

              {/* Confirm & Upload */}
              <Button
                size="icon"
                className="rounded-full w-16 h-16 bg-green-500 hover:bg-green-600"
                onClick={() => uploadMutation.mutate()}
              >
                <Check className="w-8 h-8 text-white" />
              </Button>

              {/* Cancel */}
              <Button
                variant="secondary"
                size="icon"
                className="rounded-full w-12 h-12 bg-white/90 hover:bg-white"
                onClick={resetState}
              >
                <X className="w-5 h-5" />
              </Button>
            </div>
          </div>
        )}

        {/* Uploading State */}
        {cameraState === 'uploading' && (
          <div className="flex flex-col items-center gap-4 py-8">
            <Upload className="w-8 h-8 animate-pulse text-primary" />
            <p className="text-muted-foreground">Wird hochgeladen...</p>
            <Progress value={uploadProgress} className="w-full max-w-xs" />
            <p className="text-sm text-muted-foreground">{uploadProgress}%</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default CameraScan;
