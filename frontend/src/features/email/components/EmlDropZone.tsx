/**
 * EmlDropZone - Drag-and-Drop-Zone für .eml/.msg-Dateien.
 *
 * Zeigt ein Overlay beim Ziehen von Dateien und validiert Dateitypen.
 */

import { useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const ACCEPTED_EXTENSIONS = ['.eml', '.msg'];

interface EmlDropZoneProps {
  onFilesAccepted: (files: File[]) => void;
  onError?: (message: string) => void;
  className?: string;
  disabled?: boolean;
  children: ReactNode;
}

export function EmlDropZone({
  onFilesAccepted,
  onError,
  className,
  disabled = false,
  children,
}: EmlDropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const dragCounterRef = useRef(0);
  const zoneRef = useRef<HTMLDivElement>(null);

  const isValidFile = useCallback((file: File): boolean => {
    const name = file.name.toLowerCase();
    return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
  }, []);

  const handleDragEnter = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (disabled) return;

      dragCounterRef.current += 1;
      if (dragCounterRef.current === 1) {
        setIsDragOver(true);
      }
    },
    [disabled],
  );

  const handleDragLeave = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (disabled) return;

      dragCounterRef.current -= 1;
      if (dragCounterRef.current === 0) {
        setIsDragOver(false);
      }
    },
    [disabled],
  );

  const handleDragOver = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (disabled) return;
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
    },
    [disabled],
  );

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounterRef.current = 0;
      setIsDragOver(false);
      if (disabled) return;

      const droppedFiles = Array.from(e.dataTransfer?.files ?? []);
      if (droppedFiles.length === 0) return;

      const validFiles = droppedFiles.filter(isValidFile);
      const invalidCount = droppedFiles.length - validFiles.length;

      if (invalidCount > 0) {
        onError?.('Nur .eml und .msg Dateien werden unterstützt');
      }

      if (validFiles.length > 0) {
        setIsProcessing(true);
        // Small delay so the processing state is visible
        requestAnimationFrame(() => {
          onFilesAccepted(validFiles);
          setIsProcessing(false);
        });
      }
    },
    [disabled, isValidFile, onFilesAccepted, onError],
  );

  useEffect(() => {
    const zone = zoneRef.current;
    if (!zone) return;

    zone.addEventListener('dragenter', handleDragEnter);
    zone.addEventListener('dragleave', handleDragLeave);
    zone.addEventListener('dragover', handleDragOver);
    zone.addEventListener('drop', handleDrop);

    return () => {
      zone.removeEventListener('dragenter', handleDragEnter);
      zone.removeEventListener('dragleave', handleDragLeave);
      zone.removeEventListener('dragover', handleDragOver);
      zone.removeEventListener('drop', handleDrop);
    };
  }, [handleDragEnter, handleDragLeave, handleDragOver, handleDrop]);

  return (
    <div ref={zoneRef} className={cn('relative', className)}>
      {children}

      <AnimatePresence>
        {isDragOver && !disabled && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 z-50 flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-primary bg-primary/10 backdrop-blur-sm"
          >
            <Mail className="h-12 w-12 text-primary mb-3" />
            <p className="text-lg font-medium text-primary">
              E-Mail-Dateien hier ablegen
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              .eml und .msg Dateien werden unterstützt
            </p>
          </motion.div>
        )}

        {isProcessing && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 z-50 flex flex-col items-center justify-center rounded-lg bg-background/80 backdrop-blur-sm"
          >
            <Loader2 className="h-10 w-10 animate-spin text-primary mb-3" />
            <p className="text-sm font-medium text-muted-foreground">
              Dateien werden verarbeitet...
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
