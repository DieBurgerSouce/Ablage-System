import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import {
    useReactTable,
    getCoreRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    flexRender,
    createColumnHelper,
    type SortingState,
} from '@tanstack/react-table';
import {
    CheckCircle2,
    Clock,
    Layers,
    MoreHorizontal,
    Eye,
    Play,
    CheckCheck,
    Plus,
    FileText,
    BarChart3,
    ClipboardEdit,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { trainingService, type TrainingBatch } from '@/lib/api/services/training';

const columnHelper = createColumnHelper<TrainingBatch>();

const statusConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive'; icon: typeof CheckCircle2 }> = {
    draft: { label: 'Entwurf', variant: 'secondary', icon: FileText },
    ready: { label: 'Bereit', variant: 'outline', icon: Clock },
    in_progress: { label: 'In Bearbeitung', variant: 'default', icon: Play },
    completed: { label: 'Abgeschlossen', variant: 'default', icon: CheckCircle2 },
};

interface CreateBatchFormData {
    name: string;
    description: string;
    batch_type: string;
    target_size: number;
    auto_populate: boolean;
    languages: string[];
    require_umlauts: boolean;
}

export function BatchesList() {
    const [sorting, setSorting] = useState<SortingState>([]);
    const [statusFilter, setStatusFilter] = useState<string>('');
    const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
    const [formData, setFormData] = useState<CreateBatchFormData>({
        name: '',
        description: '',
        batch_type: 'random',
        target_size: 50,
        auto_populate: true,
        languages: [],
        require_umlauts: false,
    });
    const queryClient = useQueryClient();
    const navigate = useNavigate();

    const { data, isLoading } = useQuery({
        queryKey: ['training', 'batches', statusFilter],
        queryFn: () =>
            trainingService.listBatches({
                status: statusFilter || undefined,
                limit: 50,
            }),
    });

    const createMutation = useMutation({
        mutationFn: trainingService.createBatch,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['training', 'batches'] });
            setIsCreateDialogOpen(false);
            setFormData({
                name: '',
                description: '',
                batch_type: 'random',
                target_size: 50,
                auto_populate: true,
                languages: [],
                require_umlauts: false,
            });
        },
    });

    const startMutation = useMutation({
        mutationFn: trainingService.startBatch,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['training', 'batches'] });
        },
    });

    const completeMutation = useMutation({
        mutationFn: trainingService.completeBatch,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['training', 'batches'] });
        },
    });

    const columns = [
        columnHelper.accessor('name', {
            header: 'Name',
            cell: (info) => (
                <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-muted-foreground" />
                    <span className="font-medium">{info.getValue()}</span>
                </div>
            ),
        }),
        columnHelper.accessor('status', {
            header: 'Status',
            cell: (info) => {
                const status = info.getValue();
                const config = statusConfig[status] || statusConfig.draft;
                const Icon = config.icon;
                return (
                    <Badge variant={config.variant} className="gap-1">
                        <Icon className="w-3 h-3" />
                        {config.label}
                    </Badge>
                );
            },
        }),
        columnHelper.accessor('batch_type', {
            header: 'Typ',
            cell: (info) => {
                const type = info.getValue();
                const typeLabels: Record<string, string> = {
                    random: 'Zufällig',
                    stratified: 'Stratifiziert',
                    targeted: 'Gezielt',
                };
                return <Badge variant="outline">{typeLabels[type] || type}</Badge>;
            },
        }),
        columnHelper.display({
            id: 'progress',
            header: 'Fortschritt',
            cell: ({ row }) => {
                const batch = row.original;
                const total = batch.actual_size || batch.target_size;
                const completed = batch.items_completed || 0;
                const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
                return (
                    <div className="w-32 space-y-1">
                        <Progress value={percentage} className="h-2" />
                        <div className="text-xs text-muted-foreground text-center">
                            {completed} / {total} ({percentage}%)
                        </div>
                    </div>
                );
            },
        }),
        columnHelper.accessor('target_size', {
            header: 'Zielgröße',
            cell: (info) => info.getValue().toLocaleString('de-DE'),
        }),
        columnHelper.accessor('created_at', {
            header: 'Erstellt',
            cell: (info) => {
                const date = new Date(info.getValue());
                return date.toLocaleDateString('de-DE', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                });
            },
        }),
        columnHelper.display({
            id: 'actions',
            cell: ({ row }) => {
                const batch = row.original;
                return (
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 p-0">
                                <MoreHorizontal className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => console.log('View', batch.id)}>
                                <Eye className="mr-2 h-4 w-4" />
                                Details anzeigen
                            </DropdownMenuItem>
                            {(batch.status === 'in_progress' || batch.status === 'ready') && (
                                <DropdownMenuItem
                                    onClick={() => navigate({ to: '/admin/ocr-training/batch/$id', params: { id: batch.id } })}
                                >
                                    <ClipboardEdit className="mr-2 h-4 w-4" />
                                    Bearbeiten
                                </DropdownMenuItem>
                            )}
                            {batch.status === 'ready' && (
                                <DropdownMenuItem
                                    onClick={() => startMutation.mutate(batch.id)}
                                    disabled={startMutation.isPending}
                                >
                                    <Play className="mr-2 h-4 w-4" />
                                    Starten
                                </DropdownMenuItem>
                            )}
                            {batch.status === 'in_progress' && (
                                <DropdownMenuItem
                                    onClick={() => completeMutation.mutate(batch.id)}
                                    disabled={completeMutation.isPending}
                                >
                                    <CheckCheck className="mr-2 h-4 w-4" />
                                    Abschliessen
                                </DropdownMenuItem>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                );
            },
        }),
    ];

    const table = useReactTable({
        data: data?.batches || [],
        columns,
        getCoreRowModel: getCoreRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getSortedRowModel: getSortedRowModel(),
        onSortingChange: setSorting,
        state: { sorting },
    });

    const handleCreateBatch = () => {
        createMutation.mutate({
            name: formData.name,
            description: formData.description || undefined,
            batch_type: formData.batch_type,
            target_size: formData.target_size,
            auto_populate: formData.auto_populate,
            stratification_config: {
                languages: formData.languages.length > 0 ? formData.languages : undefined,
                require_umlauts: formData.require_umlauts || undefined,
            },
        });
    };

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="flex items-center gap-2">
                            <BarChart3 className="w-5 h-5" />
                            Stichproben-Batches
                        </CardTitle>
                        <CardDescription>
                            {data?.total || 0} Batches insgesamt
                        </CardDescription>
                    </div>
                    <div className="flex gap-2">
                        <Select value={statusFilter} onValueChange={setStatusFilter}>
                            <SelectTrigger className="w-[150px]">
                                <SelectValue placeholder="Status" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="">Alle</SelectItem>
                                <SelectItem value="draft">Entwurf</SelectItem>
                                <SelectItem value="ready">Bereit</SelectItem>
                                <SelectItem value="in_progress">In Bearbeitung</SelectItem>
                                <SelectItem value="completed">Abgeschlossen</SelectItem>
                            </SelectContent>
                        </Select>
                        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
                            <DialogTrigger asChild>
                                <Button className="gap-2">
                                    <Plus className="w-4 h-4" />
                                    Neuer Batch
                                </Button>
                            </DialogTrigger>
                            <DialogContent className="sm:max-w-[500px]">
                                <DialogHeader>
                                    <DialogTitle>Neuen Stichproben-Batch erstellen</DialogTitle>
                                    <DialogDescription>
                                        Erstellen Sie einen neuen Batch für die Qualitätskontrolle.
                                    </DialogDescription>
                                </DialogHeader>
                                <div className="grid gap-4 py-4">
                                    <div className="grid gap-2">
                                        <Label htmlFor="name">Name</Label>
                                        <Input
                                            id="name"
                                            value={formData.name}
                                            onChange={(e) =>
                                                setFormData({ ...formData, name: e.target.value })
                                            }
                                            placeholder="z.B. Wöchentliche Stichprobe KW 48"
                                        />
                                    </div>
                                    <div className="grid gap-2">
                                        <Label htmlFor="description">Beschreibung (optional)</Label>
                                        <Textarea
                                            id="description"
                                            value={formData.description}
                                            onChange={(e) =>
                                                setFormData({ ...formData, description: e.target.value })
                                            }
                                            placeholder="Kurze Beschreibung des Batches..."
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="grid gap-2">
                                            <Label htmlFor="batch_type">Batch-Typ</Label>
                                            <Select
                                                value={formData.batch_type}
                                                onValueChange={(value) =>
                                                    setFormData({ ...formData, batch_type: value })
                                                }
                                            >
                                                <SelectTrigger>
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="random">Zufällig</SelectItem>
                                                    <SelectItem value="stratified">Stratifiziert</SelectItem>
                                                    <SelectItem value="targeted">Gezielt</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="grid gap-2">
                                            <Label htmlFor="target_size">Zielgröße</Label>
                                            <Input
                                                id="target_size"
                                                type="number"
                                                min={1}
                                                max={1000}
                                                value={formData.target_size}
                                                onChange={(e) =>
                                                    setFormData({
                                                        ...formData,
                                                        target_size: parseInt(e.target.value) || 50,
                                                    })
                                                }
                                            />
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            id="auto_populate"
                                            checked={formData.auto_populate}
                                            onChange={(e) =>
                                                setFormData({ ...formData, auto_populate: e.target.checked })
                                            }
                                            className="h-4 w-4 rounded border-gray-300"
                                        />
                                        <Label htmlFor="auto_populate" className="text-sm font-normal">
                                            Automatisch mit Samples befüllen
                                        </Label>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            id="require_umlauts"
                                            checked={formData.require_umlauts}
                                            onChange={(e) =>
                                                setFormData({ ...formData, require_umlauts: e.target.checked })
                                            }
                                            className="h-4 w-4 rounded border-gray-300"
                                        />
                                        <Label htmlFor="require_umlauts" className="text-sm font-normal">
                                            Nur Samples mit Umlauten
                                        </Label>
                                    </div>
                                </div>
                                <DialogFooter>
                                    <Button
                                        variant="outline"
                                        onClick={() => setIsCreateDialogOpen(false)}
                                    >
                                        Abbrechen
                                    </Button>
                                    <Button
                                        onClick={handleCreateBatch}
                                        disabled={!formData.name || createMutation.isPending}
                                    >
                                        {createMutation.isPending ? 'Erstelle...' : 'Erstellen'}
                                    </Button>
                                </DialogFooter>
                            </DialogContent>
                        </Dialog>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {isLoading ? (
                    <div className="flex items-center justify-center h-32">
                        <div className="animate-pulse text-muted-foreground">Lade Batches...</div>
                    </div>
                ) : (
                    <>
                        <Table>
                            <TableHeader>
                                {table.getHeaderGroups().map((headerGroup) => (
                                    <TableRow key={headerGroup.id}>
                                        {headerGroup.headers.map((header) => (
                                            <TableHead key={header.id}>
                                                {header.isPlaceholder
                                                    ? null
                                                    : flexRender(header.column.columnDef.header, header.getContext())}
                                            </TableHead>
                                        ))}
                                    </TableRow>
                                ))}
                            </TableHeader>
                            <TableBody>
                                {table.getRowModel().rows.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={columns.length} className="text-center text-muted-foreground">
                                            Keine Batches gefunden
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    table.getRowModel().rows.map((row) => (
                                        <TableRow key={row.id}>
                                            {row.getVisibleCells().map((cell) => (
                                                <TableCell key={cell.id}>
                                                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                                </TableCell>
                                            ))}
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                        <div className="flex items-center justify-between mt-4">
                            <div className="text-sm text-muted-foreground">
                                Seite {table.getState().pagination.pageIndex + 1} von{' '}
                                {table.getPageCount()}
                            </div>
                            <div className="flex gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => table.previousPage()}
                                    disabled={!table.getCanPreviousPage()}
                                >
                                    Zurück
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => table.nextPage()}
                                    disabled={!table.getCanNextPage()}
                                >
                                    Weiter
                                </Button>
                            </div>
                        </div>
                    </>
                )}
            </CardContent>
        </Card>
    );
}
