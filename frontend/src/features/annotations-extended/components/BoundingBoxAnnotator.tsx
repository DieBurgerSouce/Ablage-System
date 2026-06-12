import { useState, useRef, useCallback } from "react";
import { Paintbrush, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { BoundingBox } from "../types/annotations-extended-types";
import { DEFAULT_BOX_COLORS } from "../types/annotations-extended-types";

interface BoundingBoxAnnotatorProps {
  documentId: number;
  page: number;
  imageUrl: string;
  existingBoxes: BoundingBox[];
  onBoxCreated: (box: {
    x: number;
    y: number;
    width: number;
    height: number;
    label: string;
    color: string;
    comment?: string;
  }) => void;
}

interface DraftBox {
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
}

export function BoundingBoxAnnotator({
  documentId: _documentId,
  page,
  imageUrl,
  existingBoxes,
  onBoxCreated,
}: BoundingBoxAnnotatorProps) {
  const [isDrawing, setIsDrawing] = useState(false);
  const [draftBox, setDraftBox] = useState<DraftBox | null>(null);
  const [showLabelDialog, setShowLabelDialog] = useState(false);
  const [selectedColor, setSelectedColor] = useState(DEFAULT_BOX_COLORS[0]);
  const [label, setLabel] = useState("");
  const [comment, setComment] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setIsDrawing(true);
    setDraftBox({
      startX: x,
      startY: y,
      currentX: x,
      currentY: y,
    });
  }, []);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!isDrawing || !draftBox || !containerRef.current) return;

      const rect = containerRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      setDraftBox({
        ...draftBox,
        currentX: x,
        currentY: y,
      });
    },
    [isDrawing, draftBox]
  );

  const handleMouseUp = useCallback(() => {
    if (!isDrawing || !draftBox) return;

    const width = Math.abs(draftBox.currentX - draftBox.startX);
    const height = Math.abs(draftBox.currentY - draftBox.startY);

    // Only create box if it has some size
    if (width > 10 && height > 10) {
      setShowLabelDialog(true);
    } else {
      setDraftBox(null);
    }

    setIsDrawing(false);
  }, [isDrawing, draftBox]);

  const handleCreateBox = () => {
    if (!draftBox || !imageRef.current) return;

    // Calculate normalized coordinates (0-1)
    const imgWidth = imageRef.current.width;
    const imgHeight = imageRef.current.height;

    const x = Math.min(draftBox.startX, draftBox.currentX) / imgWidth;
    const y = Math.min(draftBox.startY, draftBox.currentY) / imgHeight;
    const width = Math.abs(draftBox.currentX - draftBox.startX) / imgWidth;
    const height = Math.abs(draftBox.currentY - draftBox.startY) / imgHeight;

    onBoxCreated({
      x,
      y,
      width,
      height,
      label,
      color: selectedColor,
      comment: comment || undefined,
    });

    // Reset state
    setDraftBox(null);
    setShowLabelDialog(false);
    setLabel("");
    setComment("");
  };

  const handleCancelBox = () => {
    setDraftBox(null);
    setShowLabelDialog(false);
    setLabel("");
    setComment("");
  };

  const getDraftBoxStyle = (): React.CSSProperties | undefined => {
    if (!draftBox) return undefined;

    const x = Math.min(draftBox.startX, draftBox.currentX);
    const y = Math.min(draftBox.startY, draftBox.currentY);
    const width = Math.abs(draftBox.currentX - draftBox.startX);
    const height = Math.abs(draftBox.currentY - draftBox.startY);

    return {
      position: "absolute",
      left: `${x}px`,
      top: `${y}px`,
      width: `${width}px`,
      height: `${height}px`,
      border: `2px solid ${selectedColor}`,
      backgroundColor: `${selectedColor}22`,
      pointerEvents: "none",
      zIndex: 10,
    };
  };

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm">
              <Paintbrush className="w-4 h-4 mr-2" />
              Farbe
              <div
                className="w-4 h-4 ml-2 rounded border"
                style={{ backgroundColor: selectedColor }}
              />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-2">
            <div className="grid grid-cols-3 gap-2">
              {DEFAULT_BOX_COLORS.map((color) => (
                <button
                  key={color}
                  className="w-8 h-8 rounded border-2 transition-transform hover:scale-110"
                  style={{
                    backgroundColor: color,
                    borderColor:
                      color === selectedColor ? "#000" : "transparent",
                  }}
                  onClick={() => setSelectedColor(color)}
                />
              ))}
            </div>
          </PopoverContent>
        </Popover>

        <div className="text-sm text-muted-foreground">
          Klicken und ziehen, um eine Bounding-Box zu erstellen
        </div>
      </div>

      {/* Image Container with Overlay */}
      <div
        ref={containerRef}
        className="relative inline-block"
        style={{ cursor: "crosshair" }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <img
          ref={imageRef}
          src={imageUrl}
          alt={`Seite ${page}`}
          className="max-w-full h-auto"
          draggable={false}
        />

        {/* Existing Boxes */}
        {existingBoxes.map((box) => {
          if (!imageRef.current) return null;
          const imgWidth = imageRef.current.width;
          const imgHeight = imageRef.current.height;

          return (
            <div
              key={box.id}
              style={{
                position: "absolute",
                left: `${box.x * imgWidth}px`,
                top: `${box.y * imgHeight}px`,
                width: `${box.width * imgWidth}px`,
                height: `${box.height * imgHeight}px`,
                border: `2px solid ${box.color}`,
                backgroundColor: `${box.color}22`,
                pointerEvents: "none",
              }}
            >
              <div
                className="absolute -top-6 left-0 px-2 py-1 text-xs font-medium text-white rounded"
                style={{ backgroundColor: box.color }}
              >
                {box.label}
              </div>
            </div>
          );
        })}

        {/* Draft Box */}
        {draftBox && <div style={getDraftBoxStyle()} />}
      </div>

      {/* Label Dialog */}
      {showLabelDialog && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Annotation erstellen</span>
              <Button variant="ghost" size="sm" onClick={handleCancelBox}>
                <X className="w-4 h-4" />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium">Label *</label>
              <Input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="z.B. Rechnungsnummer, Datum, ..."
                className="mt-1"
              />
            </div>

            <div>
              <label className="text-sm font-medium">Kommentar (optional)</label>
              <Textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Zusätzliche Informationen..."
                rows={3}
                className="mt-1"
              />
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={handleCancelBox}>
                Abbrechen
              </Button>
              <Button onClick={handleCreateBox} disabled={!label.trim()}>
                <Plus className="w-4 h-4 mr-2" />
                Erstellen
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
