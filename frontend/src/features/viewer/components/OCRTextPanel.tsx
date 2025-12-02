import type { BoundingBox } from "./BoundingBoxOverlay";

interface OCRTextPanelProps {
    ocrData: { text: string; confidence: number; boxes?: BoundingBox[] } | undefined;
    selectedBox: BoundingBox | null;
    onBoxSelect: (box: BoundingBox | null) => void;
    onTextEdit: (id: string, text: string) => void;
}

export function OCRTextPanel({ selectedBox }: OCRTextPanelProps) {
    return (
        <div className="space-y-4">
            <h3 className="font-semibold text-lg">OCR Results</h3>
            {/* Placeholder for text content */}
            <div className="text-sm text-muted-foreground">
                Select a region to view or edit text.
            </div>
            {selectedBox && (
                <div className="p-4 border rounded-lg bg-muted/30">
                    <h4 className="font-medium mb-2">Selected Region</h4>
                    <p className="font-mono text-sm">{selectedBox.text || "No text detected"}</p>
                </div>
            )}
        </div>
    );
}
