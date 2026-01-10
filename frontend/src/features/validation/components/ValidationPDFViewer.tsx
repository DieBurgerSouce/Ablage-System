/**
 * ValidationPDFViewer
 *
 * Enterprise-Grade PDF-Viewer fuer die Validierungsseite.
 * Rendert PDFs mit pdfjs-dist und zeigt Bounding-Boxes fuer Felder an.
 *
 * Features:
 * - PDF Rendering mit react-pdf/pdfjs-dist
 * - Bounding-Box Overlay mit Confidence-Farben
 * - Field-Highlighting bei Hover
 * - Multi-Page Navigation
 * - Zoom-Support
 * - Authenticated Preview Loading
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { motion } from 'framer-motion';
import { Loader2, AlertTriangle, FileText, ImageIcon } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { ValidationFieldReview } from '../types/validation-queue.types';

import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

// PDF.js Worker konfigurieren
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString();

/**
 * BoundingBox Interface fuer Overlay
 */
interface BoundingBox {
  id: string;
  fieldKey: string;
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
  text: string;
  page?: number;
}

/**
 * Hook um Dokument-Preview mit Auth-Token zu laden.
 * Erstellt Object-URL aus Blob fuer PDF.js.
 */
function useAuthenticatedPreview(documentId: string) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    async function loadPreview() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiClient.get(`/documents/${documentId}/preview`, {
          responseType: 'blob',
        });

        if (cancelled) return;

        const blob = response.data as Blob;
        setMimeType(blob.type);
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : 'Vorschau konnte nicht geladen werden';
        setError(message);
        console.error('[ValidationPDFViewer] Load error:', err);
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    loadPreview();

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [documentId]);

  // Cleanup bei unmount
  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl]);

  return { blobUrl, isLoading, error, mimeType };
}

/**
 * Confidence-Farbe basierend auf Score
 */
function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.95) return 'oklch(0.72 0.17 145)'; // Gruen
  if (confidence >= 0.85) return 'oklch(0.82 0.15 75)';  // Gelb
  if (confidence >= 0.70) return 'oklch(0.75 0.18 50)';  // Orange
  return 'oklch(0.55 0.22 25)'; // Rot
}

/**
 * Konvertiert ValidationFieldReview zu BoundingBox
 */
function fieldsToBoundingBoxes(
  fields: ValidationFieldReview[],
  currentPage: number
): BoundingBox[] {
  return fields
    .filter((f) => f.bounding_box)
    .filter((f) => {
      // Wenn page definiert, nur Boxes fuer aktuelle Seite zeigen
      const boxPage = f.bounding_box?.page ?? 1;
      return boxPage === currentPage;
    })
    .map((f) => ({
      id: f.id,
      fieldKey: f.field_key,
      x: f.bounding_box!.x,
      y: f.bounding_box!.y,
      width: f.bounding_box!.width,
      height: f.bounding_box!.height,
      confidence: f.confidence_score || 0,
      text: f.field_label,
      page: f.bounding_box!.page,
    }));
}

const MotionRect = motion.rect;

interface ValidationBoundingBoxOverlayProps {
  boxes: BoundingBox[];
  scale: number;
  highlightedFieldKey: string | null;
  onBoxClick?: (fieldKey: string) => void;
  pageWidth: number;
  pageHeight: number;
}

/**
 * Bounding Box Overlay Komponente
 */
function ValidationBoundingBoxOverlay({
  boxes,
  scale,
  highlightedFieldKey,
  onBoxClick,
  pageWidth,
  pageHeight,
}: ValidationBoundingBoxOverlayProps) {
  if (boxes.length === 0) return null;

  return (
    <svg
      className="absolute top-0 left-0 pointer-events-none"
      style={{
        width: pageWidth * scale,
        height: pageHeight * scale,
      }}
      aria-hidden="true"
    >
      {boxes.map((box) => {
        const isHighlighted = box.fieldKey === highlightedFieldKey;
        const color = getConfidenceColor(box.confidence);

        return (
          <g key={box.id}>
            <MotionRect
              x={box.x * scale}
              y={box.y * scale}
              width={box.width * scale}
              height={box.height * scale}
              fill={color}
              fillOpacity={isHighlighted ? 0.4 : 0.15}
              stroke={color}
              strokeWidth={isHighlighted ? 3 : 1}
              style={{ pointerEvents: 'all', cursor: 'pointer' }}
              onClick={() => onBoxClick?.(box.fieldKey)}
              whileHover={{ fillOpacity: 0.3, strokeWidth: 2 }}
              animate={{
                fillOpacity: isHighlighted ? 0.4 : 0.15,
                strokeWidth: isHighlighted ? 3 : 1,
              }}
              transition={{ duration: 0.2 }}
            />
            {/* Confidence Label bei niedrigen Werten */}
            {box.confidence < 0.85 && (
              <text
                x={box.x * scale}
                y={(box.y - 4) * scale}
                fontSize={10 * scale}
                fill={color}
                className="pointer-events-none select-none"
              >
                {Math.round(box.confidence * 100)}%
              </text>
            )}
            {/* Highlighted Label */}
            {isHighlighted && (
              <text
                x={(box.x + box.width / 2) * scale}
                y={(box.y + box.height + 14) * scale}
                fontSize={11 * scale}
                fill={color}
                textAnchor="middle"
                className="pointer-events-none select-none font-medium"
              >
                {box.text}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

interface ValidationPDFViewerProps {
  documentId: string;
  fields: ValidationFieldReview[];
  highlightedFieldKey: string | null;
  onFieldClick?: (fieldKey: string) => void;
  zoom: number;
  currentPage: number;
  onPageChange: (page: number) => void;
  onNumPagesChange?: (numPages: number) => void;
}

export function ValidationPDFViewer({
  documentId,
  fields,
  highlightedFieldKey,
  onFieldClick,
  zoom,
  currentPage,
  onPageChange,
  onNumPagesChange,
}: ValidationPDFViewerProps) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageSize, setPageSize] = useState({ width: 595, height: 842 }); // A4 default
  const { blobUrl, isLoading, error, mimeType } = useAuthenticatedPreview(documentId);

  // PDF Load Handler
  const handleDocumentLoadSuccess = useCallback(
    ({ numPages: pages }: { numPages: number }) => {
      setNumPages(pages);
      onNumPagesChange?.(pages);
    },
    [onNumPagesChange]
  );

  // Page Load Handler - holt die tatsaechliche Seitengroesse
  const handlePageLoadSuccess = useCallback(
    (page: { width: number; height: number }) => {
      setPageSize({ width: page.width, height: page.height });
    },
    []
  );

  // Bounding Boxes fuer aktuelle Seite berechnen
  const boundingBoxes = useMemo(
    () => fieldsToBoundingBoxes(fields, currentPage),
    [fields, currentPage]
  );

  // Seite begrenzen auf gueltigen Bereich
  useEffect(() => {
    if (numPages && currentPage > numPages) {
      onPageChange(numPages);
    }
  }, [numPages, currentPage, onPageChange]);

  // Pruefen ob es ein Bild ist
  const isImage = mimeType?.startsWith('image/');

  // Loading State
  if (isLoading) {
    return (
      <div
        className="w-full h-full flex items-center justify-center bg-muted/30"
        role="status"
        aria-label="Lade Dokumentvorschau"
      >
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin" aria-hidden="true" />
          <span>Lade Vorschau...</span>
        </div>
      </div>
    );
  }

  // Error State
  if (error) {
    return (
      <div
        className="w-full h-full flex items-center justify-center bg-muted/30"
        role="alert"
        aria-label="Fehler beim Laden der Vorschau"
      >
        <div className="flex flex-col items-center gap-3 text-destructive">
          <AlertTriangle className="h-8 w-8" aria-hidden="true" />
          <span className="font-medium">Vorschau konnte nicht geladen werden</span>
          <span className="text-xs text-muted-foreground">{error}</span>
        </div>
      </div>
    );
  }

  // Image Viewer
  if (blobUrl && isImage) {
    return (
      <div className="w-full h-full overflow-auto bg-muted/30 flex justify-center items-start p-4">
        <div className="relative" style={{ transform: `scale(${zoom})`, transformOrigin: 'top center' }}>
          <img
            src={blobUrl}
            alt="Dokumentvorschau"
            className="max-w-none shadow-lg rounded-lg"
            onLoad={(e) => {
              const img = e.target as HTMLImageElement;
              setPageSize({ width: img.naturalWidth, height: img.naturalHeight });
            }}
          />
          <ValidationBoundingBoxOverlay
            boxes={boundingBoxes}
            scale={1}
            highlightedFieldKey={highlightedFieldKey}
            onBoxClick={onFieldClick}
            pageWidth={pageSize.width}
            pageHeight={pageSize.height}
          />
        </div>
      </div>
    );
  }

  // PDF Viewer
  if (blobUrl) {
    return (
      <div className="w-full h-full overflow-auto bg-muted/30 flex justify-center p-4">
        <Document
          file={blobUrl}
          onLoadSuccess={handleDocumentLoadSuccess}
          onLoadError={(err) => console.error('[ValidationPDFViewer] PDF Load error:', err)}
          className="shadow-lg"
          loading={
            <div className="flex items-center gap-2 text-muted-foreground p-8">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>Lade PDF...</span>
            </div>
          }
          error={
            <div className="flex items-center gap-2 text-destructive p-8">
              <AlertTriangle className="h-5 w-5" />
              <span>Fehler beim Laden des PDFs</span>
            </div>
          }
        >
          <div className="relative">
            <Page
              pageNumber={currentPage}
              scale={zoom}
              renderTextLayer={true}
              renderAnnotationLayer={true}
              onLoadSuccess={handlePageLoadSuccess}
              loading={
                <div
                  className="flex items-center justify-center bg-card"
                  style={{ width: pageSize.width * zoom, height: pageSize.height * zoom }}
                >
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              }
            />
            <ValidationBoundingBoxOverlay
              boxes={boundingBoxes}
              scale={zoom}
              highlightedFieldKey={highlightedFieldKey}
              onBoxClick={onFieldClick}
              pageWidth={pageSize.width}
              pageHeight={pageSize.height}
            />
          </div>
        </Document>
      </div>
    );
  }

  // Fallback - kein Dokument
  return (
    <div
      className="w-full h-full flex items-center justify-center bg-muted/30 text-muted-foreground"
      role="status"
    >
      <div className="text-center">
        <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" aria-hidden="true" />
        <p className="text-lg font-medium">Keine Vorschau verfügbar</p>
        <p className="text-sm">Dokument-ID: {documentId.slice(0, 12)}...</p>
      </div>
    </div>
  );
}

export default ValidationPDFViewer;
