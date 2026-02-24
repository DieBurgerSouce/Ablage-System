/**
 * AnnotationOverlay - Annotationsebene fuer den Dokument-Viewer
 *
 * Ermoeglicht das Zeichnen von Bounding Boxes auf Dokumentseiten
 * und zeigt vorhandene Annotationen als farbige Rechtecke an.
 */

import { useState, useCallback, useRef, type MouseEvent } from 'react';
import { MessageSquare, CheckCircle, Highlighter, ThumbsUp, ThumbsDown } from 'lucide-react';
import { emitChecklistComplete } from '@/features/product-tour';
import { cn } from '@/lib/utils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useCreateAnnotation } from '../hooks/use-annotations';
import { MentionInput } from './MentionInput';
import type { Annotation, AnnotationPosition, AnnotationType } from '../api/annotations-api';

interface AnnotationOverlayProps {
  documentId: string;
  page: number;
  annotations: Annotation[];
  onAnnotationClick?: (annotation: Annotation) => void;
  annotationMode?: boolean;
  className?: string;
}

interface DrawingRect {
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
}

const typeColors: Record<AnnotationType, string> = {
  comment: 'border-blue-500 bg-blue-500/10',
  highlight: 'border-yellow-500 bg-yellow-500/10',
  drawing: 'border-purple-500 bg-purple-500/10',
  approval: 'border-green-500 bg-green-500/10',
  rejection: 'border-red-500 bg-red-500/10',
};

const typeIcons: Record<AnnotationType, React.ReactNode> = {
  comment: <MessageSquare className="h-3 w-3" />,
  highlight: <Highlighter className="h-3 w-3" />,
  drawing: <MessageSquare className="h-3 w-3" />,
  approval: <ThumbsUp className="h-3 w-3" />,
  rejection: <ThumbsDown className="h-3 w-3" />,
};

const typeLabels: Record<AnnotationType, string> = {
  comment: 'Kommentar',
  highlight: 'Markierung',
  drawing: 'Zeichnung',
  approval: 'Genehmigung',
  rejection: 'Ablehnung',
};

export function AnnotationOverlay({
  documentId,
  page,
  annotations,
  onAnnotationClick,
  annotationMode = true,
  className,
}: AnnotationOverlayProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawingRect, setDrawingRect] = useState<DrawingRect | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newPosition, setNewPosition] = useState<AnnotationPosition | null>(null);
  const [newContent, setNewContent] = useState('');
  const [newType, setNewType] = useState<AnnotationType>('comment');
  const [newMentions, setNewMentions] = useState<{ userId: string; userName: string }[]>([]);

  const createMutation = useCreateAnnotation(documentId);

  const pageAnnotations = annotations.filter((a) => a.page === page);

  const getRelativePosition = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (!overlayRef.current) return { x: 0, y: 0 };
      const rect = overlayRef.current.getBoundingClientRect();
      return {
        x: ((e.clientX - rect.left) / rect.width) * 100,
        y: ((e.clientY - rect.top) / rect.height) * 100,
      };
    },
    []
  );

  const handleMouseDown = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (e.button !== 0) return; // Nur Linksklick
      const pos = getRelativePosition(e);
      setIsDrawing(true);
      setDrawingRect({ startX: pos.x, startY: pos.y, currentX: pos.x, currentY: pos.y });
    },
    [getRelativePosition]
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (!isDrawing || !drawingRect) return;
      const pos = getRelativePosition(e);
      setDrawingRect((prev) => (prev ? { ...prev, currentX: pos.x, currentY: pos.y } : null));
    },
    [isDrawing, drawingRect, getRelativePosition]
  );

  const handleMouseUp = useCallback(() => {
    if (!isDrawing || !drawingRect) return;
    setIsDrawing(false);

    const x = Math.min(drawingRect.startX, drawingRect.currentX);
    const y = Math.min(drawingRect.startY, drawingRect.currentY);
    const width = Math.abs(drawingRect.currentX - drawingRect.startX);
    const height = Math.abs(drawingRect.currentY - drawingRect.startY);

    // Mindestgroesse pruefen (mindestens 2% in jede Richtung)
    if (width < 2 || height < 2) {
      setDrawingRect(null);
      return;
    }

    setNewPosition({ x, y, width, height });
    setShowCreateForm(true);
    setDrawingRect(null);
  }, [isDrawing, drawingRect]);

  const handleCreate = useCallback(async () => {
    if (!newContent.trim() || !newPosition) return;

    await createMutation.mutateAsync({
      document_id: documentId,
      annotation_type: newType,
      content: newContent.trim(),
      page_number: page,
      position: newPosition,
      mentioned_user_ids: newMentions.length > 0 ? newMentions.map(m => m.userId) : undefined,
    });

    emitChecklistComplete('create_annotation');
    setShowCreateForm(false);
    setNewContent('');
    setNewMentions([]);
    setNewPosition(null);
  }, [newContent, newPosition, newType, newMentions, documentId, page, createMutation]);

  const handleCancelCreate = useCallback(() => {
    setShowCreateForm(false);
    setNewContent('');
    setNewMentions([]);
    setNewPosition(null);
  }, []);

  const getDrawingStyle = () => {
    if (!drawingRect) return {};
    const x = Math.min(drawingRect.startX, drawingRect.currentX);
    const y = Math.min(drawingRect.startY, drawingRect.currentY);
    const width = Math.abs(drawingRect.currentX - drawingRect.startX);
    const height = Math.abs(drawingRect.currentY - drawingRect.startY);
    return { left: `${x}%`, top: `${y}%`, width: `${width}%`, height: `${height}%` };
  };

  return (
    <div
      ref={overlayRef}
      className={cn(
        'absolute inset-0',
        annotationMode ? 'cursor-crosshair' : 'pointer-events-none',
        className
      )}
      onMouseDown={annotationMode ? handleMouseDown : undefined}
      onMouseMove={annotationMode ? handleMouseMove : undefined}
      onMouseUp={annotationMode ? handleMouseUp : undefined}
    >
      {/* Bestehende Annotationen */}
      {pageAnnotations.map((annotation) => (
        <div
          key={annotation.id}
          className={cn(
            'absolute border-2 rounded-sm cursor-pointer transition-all hover:shadow-md pointer-events-auto',
            typeColors[annotation.annotation_type],
            annotation.is_resolved && 'opacity-40'
          )}
          style={{
            left: `${annotation.position.x}%`,
            top: `${annotation.position.y}%`,
            width: `${annotation.position.width}%`,
            height: `${annotation.position.height}%`,
          }}
          onClick={(e) => {
            e.stopPropagation();
            onAnnotationClick?.(annotation);
          }}
          title={`${typeLabels[annotation.annotation_type]}: ${annotation.content.substring(0, 60)}`}
        >
          <div className="absolute -top-5 -left-0.5 flex items-center gap-1">
            <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4 gap-0.5">
              {typeIcons[annotation.annotation_type]}
              {annotation.user_name || 'Unbekannt'}
            </Badge>
            {annotation.is_resolved && (
              <CheckCircle className="h-3 w-3 text-green-500" />
            )}
          </div>
        </div>
      ))}

      {/* Zeichenrechteck */}
      {isDrawing && drawingRect && (
        <div
          className="absolute border-2 border-dashed border-primary bg-primary/5 rounded-sm pointer-events-none"
          style={getDrawingStyle()}
        />
      )}

      {/* Annotation-Erstellungsformular */}
      {showCreateForm && newPosition && (
        <div
          className="absolute z-50"
          style={{
            left: `${newPosition.x}%`,
            top: `${newPosition.y + newPosition.height + 1}%`,
          }}
        >
          <Popover open={showCreateForm} onOpenChange={(open) => !open && handleCancelCreate()}>
            <PopoverTrigger asChild>
              <div />
            </PopoverTrigger>
            <PopoverContent className="w-72" side="bottom" align="start">
              <div className="space-y-3">
                <h4 className="font-medium text-sm">Neue Annotation</h4>
                <div className="flex gap-1">
                  {(['comment', 'highlight', 'approval', 'rejection'] as AnnotationType[]).map(
                    (type) => (
                      <Button
                        key={type}
                        variant={newType === type ? 'default' : 'ghost'}
                        size="sm"
                        className="h-7 px-2"
                        onClick={() => setNewType(type)}
                        title={typeLabels[type]}
                      >
                        {typeIcons[type]}
                      </Button>
                    )
                  )}
                </div>
                <MentionInput
                  value={newContent}
                  onChange={setNewContent}
                  mentions={newMentions}
                  onMentionsChange={setNewMentions}
                  placeholder="Kommentar eingeben... (@erwaehnen)"
                  hideSubmitButton
                  hideHint
                  disabled={createMutation.isPending}
                />
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" size="sm" onClick={handleCancelCreate}>
                    Abbrechen
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleCreate}
                    disabled={!newContent.trim() || createMutation.isPending}
                  >
                    {createMutation.isPending ? 'Speichert...' : 'Speichern'}
                  </Button>
                </div>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      )}
    </div>
  );
}
