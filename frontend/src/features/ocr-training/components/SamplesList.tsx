import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
    FileText,
    MoreHorizontal,
    Eye,
    Edit2,
    Trash2,
    XCircle,
    Languages,
    Table as TableIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { trainingService, type TrainingSample } from '@/lib/api/services/training';

const columnHelper = createColumnHelper<TrainingSample>();

const statusConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive'; icon: typeof CheckCircle2 }> = {
    pending: { label: 'Ausstehend', variant: 'secondary', icon: Clock },
    annotated: { label: 'Annotiert', variant: 'outline', icon: Edit2 },
    verified: { label: 'Verifiziert', variant: 'default', icon: CheckCircle2 },
    rejected: { label: 'Abgelehnt', variant: 'destructive', icon: XCircle },
};

export function SamplesList() {
    const [sorting, setSorting] = useState<SortingState>([]);
    const [statusFilter, setStatusFilter] = useState<string>('');
    const [languageFilter, setLanguageFilter] = useState<string>('');
    const queryClient = useQueryClient();

    const { data, isLoading } = useQuery({
        queryKey: ['training', 'samples', statusFilter, languageFilter],
        queryFn: () =>
            trainingService.listSamples({
                status: statusFilter || undefined,
                language: languageFilter || undefined,
                limit: 50,
            }),
    });

    const deleteMutation = useMutation({
        mutationFn: trainingService.deleteSample,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['training', 'samples'] });
        },
    });

    const columns = [
        columnHelper.accessor('file_path', {
            header: 'Datei',
            cell: (info) => {
                const path = info.getValue();
                const filename = path.split(/[/\\]/).pop() || path;
                return (
                    <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-muted-foreground" />
                        <span className="font-medium truncate max-w-[200px]" title={path}>
                            {filename}
                        </span>
                    </div>
                );
            },
        }),
        columnHelper.accessor('status', {
            header: 'Status',
            cell: (info) => {
                const status = info.getValue();
                const config = statusConfig[status] || statusConfig.pending;
                const Icon = config.icon;
                return (
                    <Badge variant={config.variant} className="gap-1">
                        <Icon className="w-3 h-3" />
                        {config.label}
                    </Badge>
                );
            },
        }),
        columnHelper.accessor('language', {
            header: 'Sprache',
            cell: (info) => (
                <Badge variant="outline" className="uppercase">
                    {info.getValue()}
                </Badge>
            ),
        }),
        columnHelper.accessor('document_type', {
            header: 'Typ',
            cell: (info) => info.getValue() || '-',
        }),
        columnHelper.display({
            id: 'features',
            header: 'Merkmale',
            cell: ({ row }) => {
                const sample = row.original;
                return (
                    <div className="flex gap-1">
                        {sample.has_umlauts && (
                            <Badge variant="secondary" className="text-xs" title="Enthält Umlaute">
                                <Languages className="w-3 h-3" />
                            </Badge>
                        )}
                        {sample.has_tables && (
                            <Badge variant="secondary" className="text-xs" title="Enthält Tabellen">
                                <TableIcon className="w-3 h-3" />
                            </Badge>
                        )}
                        {sample.has_fraktur && (
                            <Badge variant="secondary" className="text-xs">
                                Fraktur
                            </Badge>
                        )}
                    </div>
                );
            },
        }),
        columnHelper.accessor('ground_truth_text', {
            header: 'Ground Truth',
            cell: (info) => {
                const text = info.getValue();
                if (!text) return <span className="text-muted-foreground">-</span>;
                return (
                    <span className="text-sm truncate max-w-[200px] block" title={text}>
                        {text.substring(0, 50)}...
                    </span>
                );
            },
        }),
        columnHelper.display({
            id: 'actions',
            cell: ({ row }) => (
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8 p-0">
                            <MoreHorizontal className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => console.log('View', row.original.id)}>
                            <Eye className="mr-2 h-4 w-4" />
                            Ansehen
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => console.log('Edit', row.original.id)}>
                            <Edit2 className="mr-2 h-4 w-4" />
                            Bearbeiten
                        </DropdownMenuItem>
                        <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={() => {
                                if (confirm('Sample wirklich löschen?')) {
                                    deleteMutation.mutate(row.original.id);
                                }
                            }}
                        >
                            <Trash2 className="mr-2 h-4 w-4" />
                            Löschen
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            ),
        }),
    ];

    const table = useReactTable({
        data: data?.samples || [],
        columns,
        getCoreRowModel: getCoreRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
        getSortedRowModel: getSortedRowModel(),
        onSortingChange: setSorting,
        state: { sorting },
    });

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle>Ground Truth Samples</CardTitle>
                        <CardDescription>
                            {data?.total || 0} Samples insgesamt
                        </CardDescription>
                    </div>
                    <div className="flex gap-2">
                        <Select value={statusFilter} onValueChange={setStatusFilter}>
                            <SelectTrigger className="w-[150px]">
                                <SelectValue placeholder="Status" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="">Alle</SelectItem>
                                <SelectItem value="pending">Ausstehend</SelectItem>
                                <SelectItem value="annotated">Annotiert</SelectItem>
                                <SelectItem value="verified">Verifiziert</SelectItem>
                                <SelectItem value="rejected">Abgelehnt</SelectItem>
                            </SelectContent>
                        </Select>
                        <Select value={languageFilter} onValueChange={setLanguageFilter}>
                            <SelectTrigger className="w-[120px]">
                                <SelectValue placeholder="Sprache" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="">Alle</SelectItem>
                                <SelectItem value="de">DE</SelectItem>
                                <SelectItem value="en">EN</SelectItem>
                                <SelectItem value="nl">NL</SelectItem>
                                <SelectItem value="pl">PL</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                {isLoading ? (
                    <div className="flex items-center justify-center h-32">
                        <div className="animate-pulse text-muted-foreground">Lade Samples...</div>
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
                                            Keine Samples gefunden
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
