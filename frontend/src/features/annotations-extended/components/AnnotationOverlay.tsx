import { useRef } from "react";
import type { BoundingBox } from "../types/annotations-extended-types";

interface AnnotationOverlayProps {
  boxes: BoundingBox[];
  selectedBoxId?: number;
  onBoxClick?: (boxId: number) => void;
  imageUrl: string;
  page: number;
}

export function AnnotationOverlay({
  boxes,
  selectedBoxId,
  onBoxClick,
  imageUrl,
  page,
}: AnnotationOverlayProps) {
  const imageRef = useRef<HTMLImageElement>(null);

  return (
    <div className="relative inline-block">
      <img
        ref={imageRef}
        src={imageUrl}
        alt={`Seite ${page}`}
        className="max-w-full h-auto"
        draggable={false}
      />

      {/* Bounding Boxes */}
      {boxes.map((box) => {
        if (!imageRef.current) return null;
        const imgWidth = imageRef.current.width;
        const imgHeight = imageRef.current.height;

        const isSelected = box.id === selectedBoxId;

        return (
          <div
            key={box.id}
            role="button"
            tabIndex={0}
            style={{
              position: "absolute",
              left: `${box.x * imgWidth}px`,
              top: `${box.y * imgHeight}px`,
              width: `${box.width * imgWidth}px`,
              height: `${box.height * imgHeight}px`,
              border: `${isSelected ? "3px" : "2px"} solid ${box.color}`,
              backgroundColor: `${box.color}${isSelected ? "33" : "22"}`,
              cursor: onBoxClick ? "pointer" : "default",
              transition: "all 0.2s",
              zIndex: isSelected ? 20 : 10,
            }}
            onClick={() => onBoxClick?.(box.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                onBoxClick?.(box.id);
              }
            }}
            className="hover:scale-[1.02]"
          >
            {/* Label */}
            <div
              className="absolute -top-7 left-0 px-2 py-1 text-xs font-medium text-white rounded shadow-sm"
              style={{
                backgroundColor: box.color,
                fontSize: isSelected ? "0.8rem" : "0.75rem",
              }}
            >
              {box.label}
            </div>

            {/* Comment Preview (on hover) */}
            {box.comment && (
              <div
                className="absolute top-full left-0 mt-1 max-w-xs px-2 py-1 text-xs bg-gray-900 text-white rounded shadow-lg opacity-0 hover:opacity-100 transition-opacity pointer-events-none"
                style={{ zIndex: 30 }}
              >
                {box.comment}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
