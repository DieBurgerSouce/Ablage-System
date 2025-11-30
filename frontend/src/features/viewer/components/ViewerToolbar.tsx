import { Button } from "@/components/ui/button";
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight } from "lucide-react";

interface ViewerToolbarProps {
    currentPage: number;
    numPages: number | null;
    scale: number;
    onPageChange: (page: number) => void;
    onZoomIn: () => void;
    onZoomOut: () => void;
}

export function ViewerToolbar({ currentPage, numPages, scale, onPageChange, onZoomIn, onZoomOut }: ViewerToolbarProps) {
    return (
        <div className="flex items-center justify-between p-2 border-b bg-background">
            <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" onClick={() => onPageChange(Math.max(1, currentPage - 1))} disabled={currentPage <= 1}>
                    <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-sm">
                    Page {currentPage} of {numPages || '--'}
                </span>
                <Button variant="ghost" size="icon" onClick={() => onPageChange(Math.min(numPages || 1, currentPage + 1))} disabled={!numPages || currentPage >= numPages}>
                    <ChevronRight className="w-4 h-4" />
                </Button>
            </div>
            <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" onClick={onZoomOut}>
                    <ZoomOut className="w-4 h-4" />
                </Button>
                <span className="text-sm w-12 text-center">{Math.round(scale * 100)}%</span>
                <Button variant="ghost" size="icon" onClick={onZoomIn}>
                    <ZoomIn className="w-4 h-4" />
                </Button>
            </div>
        </div>
    );
}
