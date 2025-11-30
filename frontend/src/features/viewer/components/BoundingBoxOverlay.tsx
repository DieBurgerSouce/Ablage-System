import { motion } from 'framer-motion';

export interface BoundingBox {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    confidence: number;
    text?: string;
}

function getConfidenceColor(confidence: number): string {
    if (confidence >= 0.95) return 'oklch(0.72 0.17 145)'; // Green
    if (confidence >= 0.85) return 'oklch(0.82 0.15 75)';  // Yellow
    if (confidence >= 0.70) return 'oklch(0.75 0.18 50)';  // Orange
    return 'oklch(0.55 0.22 25)'; // Red
}

interface BoundingBoxOverlayProps {
    boxes: BoundingBox[];
    scale: number;
    selectedBox: BoundingBox | null;
    onBoxClick: (box: BoundingBox) => void;
}

export function BoundingBoxOverlay({ boxes, scale, selectedBox, onBoxClick }: BoundingBoxOverlayProps) {
    return (
        <svg
            className="absolute top-0 left-0 pointer-events-none"
            style={{ width: '100%', height: '100%' }}
        >
            {boxes.map((box, idx) => (
                <g key={box.id || idx}>
                    <motion.rect
                        x={box.x * scale}
                        y={box.y * scale}
                        width={box.width * scale}
                        height={box.height * scale}
                        fill={getConfidenceColor(box.confidence)}
                        fillOpacity={selectedBox?.id === box.id ? 0.4 : 0.15}
                        stroke={getConfidenceColor(box.confidence)}
                        strokeWidth={selectedBox?.id === box.id ? 3 : 1}
                        style={{ pointerEvents: 'all', cursor: 'pointer' }}
                        onClick={() => onBoxClick(box)}
                        whileHover={{ fillOpacity: 0.3, strokeWidth: 2 }}
                    />
                    {box.confidence < 0.85 && (
                        <text
                            x={box.x * scale}
                            y={(box.y - 4) * scale}
                            fontSize={10}
                            fill={getConfidenceColor(box.confidence)}
                        >
                            {Math.round(box.confidence * 100)}% ⚠️
                        </text>
                    )}
                </g>
            ))}
        </svg>
    );
}
