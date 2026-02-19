import type { SmartAnalysisResult, Tune } from '../types';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import { FileText, AlertCircle, Check, MoreVertical, Paperclip, Cpu, Sparkles, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
    DropdownMenuLabel,
    DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

interface DocumentListProps {
    results: SmartAnalysisResult[];
    onUpdateTune: (fileId: string, tuneId: string) => void;
    onUpdateBackend: (fileId: string, backendId: string) => void;
    onRemove: (fileId: string) => void;
}

const BACKEND_OPTIONS = [
    { id: 'deepseek-janus', name: 'DeepSeek Janus', icon: Sparkles },
    { id: 'got-ocr', name: 'GOT-OCR 2.0', icon: Zap },
    { id: 'surya-gpu', name: 'Surya (GPU)', icon: Zap },
    { id: 'surya-docling', name: 'Surya (CPU)', icon: Cpu },
];

export function DocumentList({ results, onUpdateTune, onUpdateBackend, onRemove }: DocumentListProps) {
    // Fetch Tunes
    const { data: tunes } = useQuery({
        queryKey: ['tunes', 'active'],
        queryFn: async () => {
            const response = await apiClient.get('/tunes?active_only=true');
            return response.data as Tune[];
        }
    });

    // Group logic: Find parents and attach children
    const parents = results.filter(r => !r.isChild);

    return (
        <div className="space-y-4" data-tour="document-list">
            <div className="grid grid-cols-[1fr_200px_200px_100px_40px] gap-4 text-sm text-muted-foreground px-4">
                <span>Dokument</span>
                <span>Kontext (Tune)</span>
                <span>OCR Engine</span>
                <span className="text-center">Status</span>
                <span></span>
            </div>

            <div className="space-y-2">
                {parents.map(parent => {
                    const children = results.filter(r => r.parentId === parent.fileId);

                    return (
                        <div key={parent.fileId} className="space-y-2">
                            <DocumentRow
                                result={parent}
                                tunes={tunes || []}
                                onUpdateTune={onUpdateTune}
                                onUpdateBackend={onUpdateBackend}
                                onRemove={onRemove}
                            />
                            {children.map(child => (
                                <DocumentRow
                                    key={child.fileId}
                                    result={child}
                                    tunes={tunes || []}
                                    onUpdateTune={onUpdateTune}
                                    onUpdateBackend={onUpdateBackend}
                                    onRemove={onRemove}
                                    isChild
                                />
                            ))}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

interface DocumentRowProps {
    result: SmartAnalysisResult;
    tunes: Tune[];
    onUpdateTune: (id: string, tuneId: string) => void;
    onUpdateBackend: (id: string, backendId: string) => void;
    onRemove: (id: string) => void;
    isChild?: boolean;
}

function DocumentRow({ result, tunes, onUpdateTune, onUpdateBackend, onRemove, isChild }: DocumentRowProps) {
    const tune = tunes.find(t => t.id === result.detectedTuneId);
    const backend = BACKEND_OPTIONS.find(b => b.id === result.selectedBackendId);

    return (
        <div className={cn(
            "grid grid-cols-[1fr_200px_200px_100px_40px] gap-4 items-center p-4 rounded-xl border bg-card transition-colors",
            isChild && "ml-8 border-l-4 border-l-primary/20 bg-muted/30"
        )}>
            <div className="flex items-center gap-3 overflow-hidden">
                <div className={cn(
                    "p-2 rounded-lg shrink-0",
                    isChild ? "bg-muted text-muted-foreground" : "bg-primary/10 text-primary"
                )}>
                    {isChild ? <Paperclip className="w-4 h-4" /> : <FileText className="w-5 h-5" />}
                </div>
                <div className="min-w-0">
                    <p className="font-medium truncate">{result.fileName}</p>
                    <p className="text-xs text-muted-foreground">
                        {(result.fileSize / 1024 / 1024).toFixed(2)} MB
                    </p>
                </div>
            </div>

            {/* Tune Selector */}
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="justify-start font-normal">
                        {tune ? (
                            <>
                                <div className={`w-2 h-2 rounded-full mr-2 ${tune.color}`} />
                                <span className="truncate">{tune.name}</span>
                            </>
                        ) : (
                            <span className="text-muted-foreground">Wählen...</span>
                        )}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-[200px]">
                    <DropdownMenuLabel>Kontext ändern</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {tunes.map(t => (
                        <DropdownMenuItem key={t.id} onClick={() => onUpdateTune(result.fileId, t.id)}>
                            <div className={`w-2 h-2 rounded-full mr-2 ${t.color}`} />
                            {t.name}
                            {t.id === result.detectedTuneId && <Check className="ml-auto w-4 h-4" />}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>

            {/* Backend Selector */}
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="justify-start font-normal">
                        {backend ? (
                            <>
                                <backend.icon className="w-3 h-3 mr-2" />
                                <span className="truncate">{backend.name}</span>
                            </>
                        ) : (
                            <span className="text-muted-foreground">Auto</span>
                        )}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-[200px]">
                    <DropdownMenuLabel>OCR Engine ändern</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    {BACKEND_OPTIONS.map(b => (
                        <DropdownMenuItem key={b.id} onClick={() => onUpdateBackend(result.fileId, b.id)}>
                            <b.icon className="w-3 h-3 mr-2" />
                            {b.name}
                            {b.id === result.selectedBackendId && <Check className="ml-auto w-4 h-4" />}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>

            <div className="text-center">
                {result.issues.length > 0 ? (
                    <Badge variant="destructive" className="gap-1">
                        <AlertCircle className="w-3 h-3" />
                        Prüfen
                    </Badge>
                ) : (
                    <Badge variant="secondary" className="bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20">
                        <Check className="w-3 h-3 mr-1" />
                        Bereit
                    </Badge>
                )}
            </div>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                        <MoreVertical className="w-4 h-4" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    <DropdownMenuItem className="text-destructive" onClick={() => onRemove(result.fileId)}>
                        Entfernen
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}
