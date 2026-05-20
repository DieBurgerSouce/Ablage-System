import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, RotateCw, Download, Printer, Highlighter, MessageSquare, MousePointer2, FileSearch, SunDim, Maximize2, Minimize2 } from 'lucide-react';
import { motion } from 'framer-motion';
import { motionTokens } from '@/lib/motion-tokens';
import { useAnnotationStore } from '../store/useAnnotationStore';
import { SimilarDocumentsDrawer } from './SimilarDocumentsDrawer';
import { PaperDimmingPopover } from './PaperDimmingPopover';

interface ViewerToolbarProps {
    documentId?: string;
    currentPage: number;
    numPages: number | null;
    scale: number;
    rotation: number;
    onPageChange: (page: number) => void;
    onZoomIn: () => void;
    onZoomOut: () => void;
    onRotate: () => void;
    onDownload: () => void;
    onPrint: () => void;
    isFocusMode?: boolean;
    onToggleFocusMode?: () => void;
}

const MotionDiv = motion.div;

export function ViewerToolbar({ documentId, currentPage, numPages, scale, rotation: _rotation, onPageChange, onZoomIn, onZoomOut, onRotate, onDownload, onPrint, isFocusMode, onToggleFocusMode }: ViewerToolbarProps) {
    const { mode, setMode } = useAnnotationStore()
    const [similarDrawerOpen, setSimilarDrawerOpen] = useState(false)

    return (
        <MotionDiv
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={motionTokens.spring.gentle}
            className="h-14 border-b bg-background/80 backdrop-blur-md flex items-center justify-between px-4 sticky top-0 z-20"
        >
            <div className="flex items-center gap-2">
                <div className="flex items-center bg-muted/50 rounded-lg p-1 border mr-2">
                    <Button
                        variant={mode === 'view' ? 'secondary' : 'ghost'}
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => setMode('view')}
                        aria-label="Auswahl-Modus"
                        title="Auswahl"
                    >
                        <MousePointer2 className="w-4 h-4" />
                    </Button>
                    <Button
                        variant={mode === 'highlight' ? 'secondary' : 'ghost'}
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => setMode('highlight')}
                        aria-label="Hervorheben-Modus"
                        title="Hervorheben"
                    >
                        <Highlighter className="w-4 h-4 text-yellow-500" />
                    </Button>
                    <Button
                        variant={mode === 'comment' ? 'secondary' : 'ghost'}
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => setMode('comment')}
                        aria-label="Kommentar-Modus"
                        title="Kommentar"
                    >
                        <MessageSquare className="w-4 h-4 text-blue-500" />
                    </Button>
                </div>
                <PaperDimmingPopover />
                <div className="w-px h-6 bg-border mx-2" />
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

                <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground" onClick={onRotate} title="Seite drehen">
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
                {documentId && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 gap-2 text-xs font-medium"
                        onClick={() => setSimilarDrawerOpen(true)}
                        title="Ähnliche Dokumente finden"
                    >
                        <FileSearch className="w-3.5 h-3.5" />
                        Ähnliche
                    </Button>
                )}
                {onToggleFocusMode && (
                    <Button
                        variant={isFocusMode ? "secondary" : "ghost"}
                        size="icon"
                        className="h-8 w-8"
                        onClick={onToggleFocusMode}
                        title={isFocusMode ? "Geteilte Ansicht" : "Fokus-Modus"}
                    >
                        {isFocusMode ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                    </Button>
                )}
                <Button variant="outline" size="sm" className="h-8 gap-2 text-xs font-medium" onClick={onDownload}>
                    <Download className="w-3.5 h-3.5" />
                    Download
                </Button>
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onPrint} title="Drucken">
                    <Printer className="w-4 h-4" />
                </Button>
            </div>

            {/* Similar Documents Drawer */}
            {documentId && (
                <SimilarDocumentsDrawer
                    documentId={documentId}
                    open={similarDrawerOpen}
                    onOpenChange={setSimilarDrawerOpen}
                />
            )}
        </MotionDiv>
    );
}
