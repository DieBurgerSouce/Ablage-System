import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, RotateCw, Download, Printer } from 'lucide-react';
import { motion } from 'framer-motion';
import { motionTokens } from '@/lib/motion-tokens';

interface ViewerToolbarProps {
    currentPage: number;
    numPages: number | null;
    scale: number;
    onPageChange: (page: number) => void;
    onZoomIn: () => void;
    onZoomOut: () => void;
}

const MotionDiv = motion.div;

export function ViewerToolbar({ currentPage, numPages, scale, onPageChange, onZoomIn, onZoomOut }: ViewerToolbarProps) {
    return (
        <MotionDiv
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={motionTokens.spring.gentle}
            className="h-14 border-b bg-background/80 backdrop-blur-md flex items-center justify-between px-4 sticky top-0 z-20"
        >
            <div className="flex items-center gap-2">
                <div className="flex items-center bg-muted/50 rounded-lg p-1 border">
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 hover:bg-background hover:shadow-sm transition-all"
                        onClick={onZoomOut}
                        disabled={scale <= 0.5}
                    >
                        <ZoomOut className="w-4 h-4" />
                    </Button>
                    <span className="w-16 text-center text-xs font-mono font-medium">
                        {Math.round(scale * 100)}%
                    </span>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 hover:bg-background hover:shadow-sm transition-all"
                        onClick={onZoomIn}
                        disabled={scale >= 3}
                    >
                        <ZoomIn className="w-4 h-4" />
                    </Button>
                </div>

                <div className="w-px h-6 bg-border mx-2" />

                <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
                    <RotateCw className="w-4 h-4" />
                </Button>
            </div>

            <div className="flex items-center gap-2 bg-muted/50 rounded-lg p-1 border">
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 hover:bg-background hover:shadow-sm transition-all"
                    onClick={() => onPageChange(Math.max(1, currentPage - 1))}
                    disabled={currentPage <= 1}
                >
                    <ChevronLeft className="w-4 h-4" />
                </Button>
                <div className="flex items-center gap-2 px-2">
                    <Input
                        type="number"
                        min={1}
                        max={numPages || 1}
                        value={currentPage}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => onPageChange(Math.min(numPages || 1, Math.max(1, parseInt(e.target.value || '1', 10) || 1)))}
                        className="h-7 w-12 text-center p-0 text-xs font-mono bg-background border-none focus-visible:ring-1"
                    />
                    <span className="text-xs text-muted-foreground font-medium">
                        / {numPages || '-'}
                    </span>
                </div>
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 hover:bg-background hover:shadow-sm transition-all"
                    onClick={() => onPageChange(Math.min(numPages || 1, currentPage + 1))}
                    disabled={!numPages || currentPage >= numPages}
                >
                    <ChevronRight className="w-4 h-4" />
                </Button>
            </div>

            <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" className="h-8 gap-2 text-xs font-medium">
                    <Download className="w-3.5 h-3.5" />
                    Download
                </Button>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                    <Printer className="w-4 h-4" />
                </Button>
            </div>
        </MotionDiv>
    );
}
