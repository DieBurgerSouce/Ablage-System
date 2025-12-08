import type { SmartAnalysisResult } from '../types';
import { AVAILABLE_TUNES } from '@/lib/api/smart-analysis';
import { FileText, AlertCircle, Check, MoreVertical, Paperclip } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface DocumentListProps {
    results: SmartAnalysisResult[];
    onUpdateTune: (fileId: string, tuneId: string) => void;
    onRemove: (fileId: string) => void;
}

export function DocumentList({ results, onUpdateTune, onRemove }: DocumentListProps) {
    // Group logic: Find parents and attach children
    const parents = results.filter(r => !r.isChild);

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between text-sm text-muted-foreground px-4">
                <span>Dokument</span>
                <div className="flex gap-12 mr-12">
                    <span>Erkannter Tune</span>
                    <span>Status</span>
                </div>
            </div>

            <div className="space-y-2">
                {parents.map(parent => {
                    const children = results.filter(r => r.parentId === parent.fileId);

                    return (
                        <div key={parent.fileId} className="space-y-2">
                            <DocumentRow
                                item={parent}
                                onUpdateTune={onUpdateTune}
                                onRemove={onRemove}
                            />
                            {children.map(child => (
                                <div key={child.fileId} className="pl-8 relative">
                                    <div className="absolute left-4 top-1/2 -translate-y-1/2 w-3 h-px bg-border" />
                                    <div className="absolute left-4 top-0 bottom-1/2 w-px bg-border" />
                                    <DocumentRow
                                        item={child}
                                        isChild
                                        onUpdateTune={onUpdateTune}
                                        onRemove={onRemove}
                                    />
                                </div>
                            ))}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function DocumentRow({ item, isChild, onUpdateTune, onRemove }: {
    item: SmartAnalysisResult,
    isChild?: boolean,
    onUpdateTune: (id: string, tuneId: string) => void,
    onRemove: (id: string) => void
}) {
    const tune = AVAILABLE_TUNES.find(t => t.id === item.detectedTuneId);

    return (
        <div className={cn(
            "group flex items-center justify-between p-3 rounded-lg border bg-card transition-all hover:shadow-sm",
            isChild && "bg-muted/30 border-dashed"
        )}>
            <div className="flex items-center gap-3 flex-1 min-w-0">
                <div className={cn(
                    "p-2 rounded flex-shrink-0",
                    item.confidence === 'high' ? "bg-emerald-500/10 text-emerald-600" :
                        item.confidence === 'medium' ? "bg-amber-500/10 text-amber-600" :
                            "bg-slate-500/10 text-slate-600"
                )}>
                    {isChild ? <Paperclip className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                </div>
                <div className="min-w-0">
                    <p className="font-medium truncate text-sm">{item.fileName}</p>
                    <p className="text-xs text-muted-foreground">
                        {Math.round(item.fileSize / 1024)} KB
                        {item.issues.length > 0 && (
                            <span className="ml-2 text-amber-600 flex items-center inline-flex gap-1">
                                <AlertCircle className="w-3 h-3" />
                                {item.issues[0]}
                            </span>
                        )}
                    </p>
                </div>
            </div>

            <div className="flex items-center gap-8 mr-2">
                <div className="w-40">
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="outline" size="sm" className="w-full justify-start text-xs h-8">
                                <span className="truncate">{tune?.name || 'Unbekannt'}</span>
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-56">
                            {AVAILABLE_TUNES.map(t => (
                                <DropdownMenuItem key={t.id} onClick={() => onUpdateTune(item.fileId, t.id)}>
                                    <span className={cn("mr-2 w-2 h-2 rounded-full", t.color)} />
                                    {t.name}
                                    {t.id === item.detectedTuneId && <Check className="ml-auto w-4 h-4" />}
                                </DropdownMenuItem>
                            ))}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>

                <div className="w-24 flex justify-center">
                    <Badge variant={
                        item.confidence === 'high' ? 'default' :
                            item.confidence === 'medium' ? 'secondary' : 'destructive'
                    } className="text-xs">
                        {item.confidence === 'high' ? 'Sicher' :
                            item.confidence === 'medium' ? 'Prüfen' : 'Unsicher'}
                    </Badge>
                </div>

                <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={() => onRemove(item.fileId)}>
                    <MoreVertical className="w-4 h-4" />
                </Button>
            </div>
        </div>
    );
}
