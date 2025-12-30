import { useRef, useState, useEffect } from 'react'
import { useAnnotationStore } from '@/features/viewer/store/useAnnotationStore'
import { cn } from '@/lib/utils'
import { MessageSquare, Trash2, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'

interface AnnotationLayerProps {
    pageNumber: number
    scale: number
    width: number
    height: number
}

export function AnnotationLayer({ pageNumber, scale, width, height }: AnnotationLayerProps) {
    const { annotations, mode, addAnnotation, removeAnnotation, updateAnnotation, selectAnnotation, selectedId } = useAnnotationStore()
    const containerRef = useRef<HTMLDivElement>(null)
    const [isDrawing, setIsDrawing] = useState(false)
    const [startPoint, setStartPoint] = useState<{ x: number, y: number } | null>(null)

    // Filter annotations for this page
    const pageAnnotations = annotations.filter(a => a.page === pageNumber)

    const getRelativeCoords = (e: React.MouseEvent) => {
        if (!containerRef.current) return { x: 0, y: 0 }
        const rect = containerRef.current.getBoundingClientRect()
        return {
            x: Math.max(0, Math.min(100, (e.clientX - rect.left) / rect.width * 100)),
            y: Math.max(0, Math.min(100, (e.clientY - rect.top) / rect.height * 100))
        }
    }

    const handleMouseDown = (e: React.MouseEvent) => {
        if (mode === 'view') return

        const coords = getRelativeCoords(e)
        setStartPoint(coords)
        setIsDrawing(true)
    }

    const handleMouseUp = (e: React.MouseEvent) => {
        if (!isDrawing || !startPoint) return

        const endCoords = getRelativeCoords(e)
        const id = crypto.randomUUID()

        if (mode === 'highlight') {
            const w = Math.abs(endCoords.x - startPoint.x)
            const h = Math.abs(endCoords.y - startPoint.y)
            const x = Math.min(startPoint.x, endCoords.x)
            const y = Math.min(startPoint.y, endCoords.y)

            if (w > 0.5 && h > 0.5) { // Min size check
                addAnnotation({
                    id,
                    page: pageNumber,
                    type: 'highlight',
                    x, y, w, h,
                    color: 'rgba(255, 226, 85, 0.4)',
                    createdAt: Date.now()
                })
            }
        } else if (mode === 'comment') {
            addAnnotation({
                id,
                page: pageNumber,
                type: 'comment',
                x: endCoords.x,
                y: endCoords.y,
                color: '#ef4444',
                content: '',
                createdAt: Date.now()
            })
            selectAnnotation(id)
        }

        setIsDrawing(false)
        setStartPoint(null)
    }

    return (
        <div
            ref={containerRef}
            className={cn(
                "absolute inset-0 z-10",
                mode === 'view' ? "pointer-events-none" : "cursor-crosshair pointer-events-auto"
            )}
            onMouseDown={handleMouseDown}
            onMouseUp={handleMouseUp}
        >
            {pageAnnotations.map(annotation => (
                <div
                    key={annotation.id}
                    className={cn(
                        "absolute group pointer-events-auto", // Always capture events on annotations themselves
                        annotation.id === selectedId && "ring-2 ring-primary ring-offset-1"
                    )}
                    style={{
                        left: `${annotation.x}%`,
                        top: `${annotation.y}%`,
                        width: annotation.w ? `${annotation.w}%` : undefined,
                        height: annotation.h ? `${annotation.h}%` : undefined,
                        backgroundColor: annotation.type === 'highlight' ? annotation.color : undefined,
                        mixBlendMode: annotation.type === 'highlight' ? 'multiply' : 'normal',
                    }}
                    onClick={(e) => {
                        e.stopPropagation()
                        selectAnnotation(annotation.id)
                    }}
                >
                    {annotation.type === 'comment' && (
                        <Popover open={selectedId === annotation.id} onOpenChange={(open) => !open && selectAnnotation(null)}>
                            <PopoverTrigger asChild>
                                <div className="relative -ml-3 -mt-3 p-1.5 rounded-full bg-red-500 text-white shadow-md cursor-pointer hover:scale-110 transition-transform ring-2 ring-white">
                                    <MessageSquare className="w-3.5 h-3.5 fill-current" />
                                </div>
                            </PopoverTrigger>
                            <PopoverContent className="w-72 p-0 shadow-xl" align="start" sideOffset={10}>
                                <div className="flex items-center gap-2 p-3 border-b bg-muted/30">
                                    <Avatar className="w-6 h-6">
                                        <AvatarFallback className="text-[10px] bg-primary/10 text-primary">
                                            {annotation.author?.substring(0, 2).toUpperCase() || 'US'}
                                        </AvatarFallback>
                                    </Avatar>
                                    <div className="flex flex-col">
                                        <span className="text-xs font-semibold">{annotation.author || 'Unbekannt'}</span>
                                        <span className="text-[10px] text-muted-foreground">{new Date(annotation.createdAt).toLocaleString()}</span>
                                    </div>
                                </div>
                                <div className="p-3">
                                    <textarea
                                        className="w-full min-h-[80px] text-sm bg-transparent border-none resize-none focus:outline-none placeholder:text-muted-foreground/50"
                                        placeholder="Schreibe einen Kommentar..."
                                        value={annotation.content || ''}
                                        onChange={(e) => updateAnnotation(annotation.id, { content: e.target.value })}
                                        autoFocus
                                    />
                                </div>
                                <div className="p-2 border-t bg-muted/10 flex justify-between items-center">
                                    <span className="text-[10px] text-muted-foreground">Wird automatisch gespeichert</span>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                                        onClick={() => removeAnnotation(annotation.id)}
                                    >
                                        <Trash2 className="w-3 h-3 mr-1.5" />
                                        Löschen
                                    </Button>
                                </div>
                            </PopoverContent>
                        </Popover>
                    )}

                    {annotation.type === 'highlight' && (
                        <div className="absolute -right-2 -top-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                            <div className="bg-white rounded-full shadow-sm p-0.5 border" title={`Hervorgehoben von ${annotation.author}`}>
                                <User className="w-3 h-3 text-muted-foreground" />
                            </div>
                            <Button
                                variant="destructive"
                                size="icon"
                                className="h-5 w-5 rounded-full shadow-sm"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    removeAnnotation(annotation.id)
                                }}
                            >
                                <Trash2 className="w-3 h-3" />
                            </Button>
                        </div>
                    )}
                </div>
            ))}
        </div>
    )
}
