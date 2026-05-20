import type { BoundingBox } from "./BoundingBoxOverlay";

interface OCRTextPanelProps {
    ocrData: { text: string; confidence: number; boxes?: BoundingBox[] } | undefined;
    selectedBox: BoundingBox | null;
    extractedText?: string;
}

export function OCRTextPanel({ ocrData, selectedBox, extractedText }: OCRTextPanelProps) {
    // Use ocrData.text if available, otherwise fall back to extractedText
    const displayText = ocrData?.text || extractedText;

    return (
        <div className="space-y-4">
            <h3 className="font-semibold text-lg">OCR-Text</h3>

            {displayText ? (
                <div className="p-4 border rounded-lg bg-muted/30 max-h-[60vh] overflow-auto">
                    <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed">
                        {displayText}
                    </pre>
                </div>
            ) : (
                <div className="text-sm text-muted-foreground">
                    Kein OCR-Text verfügbar.
                </div>
            )}

            {selectedBox && (
                <div className="p-4 border rounded-lg bg-primary/10 border-primary/30">
                    <h4 className="font-medium mb-2">Ausgewählter Bereich</h4>
                    <p className="font-mono text-sm">{selectedBox.text || "Kein Text erkannt"}</p>
                </div>
            )}
        </div>
    );
}
