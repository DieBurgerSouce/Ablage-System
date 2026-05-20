/**
 * EnterpriseDataTable Component Stories
 *
 * Data Table Stories für Visual Regression Testing.
 * Enterprise-ready Table mit Sorting, Filtering, Pagination.
 */

import type { Meta, StoryObj } from '@storybook/react';
import { fn } from '@storybook/test';
import { ColumnDef } from '@tanstack/react-table';
import { MoreHorizontal, ArrowUpDown } from 'lucide-react';
import { EnterpriseDataTable } from '@/components/ui/data-table/EnterpriseDataTable';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

// ==================== Sample Data ====================

interface Document {
    id: string;
    name: string;
    type: string;
    status: 'verarbeitet' | 'ausstehend' | 'fehler';
    uploadedAt: string;
    size: string;
    confidence: number;
}

const sampleDocuments: Document[] = [
    {
        id: '1',
        name: 'Rechnung_2024_001.pdf',
        type: 'Rechnung',
        status: 'verarbeitet',
        uploadedAt: '2024-01-15',
        size: '245 KB',
        confidence: 0.95,
    },
    {
        id: '2',
        name: 'Lieferschein_A123.pdf',
        type: 'Lieferschein',
        status: 'verarbeitet',
        uploadedAt: '2024-01-14',
        size: '180 KB',
        confidence: 0.88,
    },
    {
        id: '3',
        name: 'Angebot_2024_Q1.pdf',
        type: 'Angebot',
        status: 'ausstehend',
        uploadedAt: '2024-01-13',
        size: '520 KB',
        confidence: 0,
    },
    {
        id: '4',
        name: 'Vertrag_Kunde_XYZ.pdf',
        type: 'Vertrag',
        status: 'fehler',
        uploadedAt: '2024-01-12',
        size: '1.2 MB',
        confidence: 0.32,
    },
    {
        id: '5',
        name: 'Bestellung_B456.pdf',
        type: 'Bestellung',
        status: 'verarbeitet',
        uploadedAt: '2024-01-11',
        size: '98 KB',
        confidence: 0.91,
    },
    {
        id: '6',
        name: 'Mahnung_M789.pdf',
        type: 'Mahnung',
        status: 'verarbeitet',
        uploadedAt: '2024-01-10',
        size: '67 KB',
        confidence: 0.97,
    },
    {
        id: '7',
        name: 'Gutschrift_G001.pdf',
        type: 'Gutschrift',
        status: 'ausstehend',
        uploadedAt: '2024-01-09',
        size: '145 KB',
        confidence: 0,
    },
    {
        id: '8',
        name: 'Rechnung_2024_002.pdf',
        type: 'Rechnung',
        status: 'verarbeitet',
        uploadedAt: '2024-01-08',
        size: '312 KB',
        confidence: 0.89,
    },
    {
        id: '9',
        name: 'Auftragsbestätigung_A001.pdf',
        type: 'Auftragsbestätigung',
        status: 'verarbeitet',
        uploadedAt: '2024-01-07',
        size: '178 KB',
        confidence: 0.94,
    },
    {
        id: '10',
        name: 'Kontoauszug_Jan2024.pdf',
        type: 'Kontoauszug',
        status: 'ausstehend',
        uploadedAt: '2024-01-06',
        size: '890 KB',
        confidence: 0,
    },
    {
        id: '11',
        name: 'Steuerbescheid_2023.pdf',
        type: 'Steuerbescheid',
        status: 'verarbeitet',
        uploadedAt: '2024-01-05',
        size: '456 KB',
        confidence: 0.82,
    },
    {
        id: '12',
        name: 'Arbeitsvertrag_Neu.pdf',
        type: 'Vertrag',
        status: 'fehler',
        uploadedAt: '2024-01-04',
        size: '2.1 MB',
        confidence: 0.15,
    },
];

// ==================== Column Definitions ====================

const columns: ColumnDef<Document>[] = [
    {
        id: 'select',
        header: ({ table }) => (
            <Checkbox
                checked={
                    table.getIsAllPageRowsSelected() ||
                    (table.getIsSomePageRowsSelected() && 'indeterminate')
                }
                onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
                aria-label="Alle auswählen"
            />
        ),
        cell: ({ row }) => (
            <Checkbox
                checked={row.getIsSelected()}
                onCheckedChange={(value) => row.toggleSelected(!!value)}
                aria-label="Zeile auswählen"
            />
        ),
        enableSorting: false,
        enableHiding: false,
    },
    {
        accessorKey: 'name',
        header: ({ column }) => (
            <Button
                variant="ghost"
                onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            >
                Name
                <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
        ),
        cell: ({ row }) => <div className="font-medium">{row.getValue('name')}</div>,
    },
    {
        accessorKey: 'type',
        header: 'Typ',
        cell: ({ row }) => <Badge variant="outline">{row.getValue('type')}</Badge>,
    },
    {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => {
            const status = row.getValue('status') as string;
            const statusColors = {
                verarbeitet: 'bg-green-100 text-green-800',
                ausstehend: 'bg-yellow-100 text-yellow-800',
                fehler: 'bg-red-100 text-red-800',
            };
            return (
                <Badge className={statusColors[status as keyof typeof statusColors]}>
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                </Badge>
            );
        },
        filterFn: (row, id, value) => {
            return value.includes(row.getValue(id));
        },
    },
    {
        accessorKey: 'confidence',
        header: 'Konfidenz',
        cell: ({ row }) => {
            const confidence = row.getValue('confidence') as number;
            if (confidence === 0) return <span className="text-muted-foreground">-</span>;
            return (
                <div className="flex items-center gap-2">
                    <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-primary"
                            style={{ width: `${confidence * 100}%` }}
                        />
                    </div>
                    <span className="text-sm">{Math.round(confidence * 100)}%</span>
                </div>
            );
        },
    },
    {
        accessorKey: 'uploadedAt',
        header: ({ column }) => (
            <Button
                variant="ghost"
                onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
            >
                Hochgeladen
                <ArrowUpDown className="ml-2 h-4 w-4" />
            </Button>
        ),
        cell: ({ row }) => {
            const date = new Date(row.getValue('uploadedAt'));
            return date.toLocaleDateString('de-DE');
        },
    },
    {
        accessorKey: 'size',
        header: 'Größe',
    },
    {
        id: 'actions',
        cell: ({ row }) => {
            const document = row.original;
            return (
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" className="h-8 w-8 p-0">
                            <span className="sr-only">Menue öffnen</span>
                            <MoreHorizontal className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuLabel>Aktionen</DropdownMenuLabel>
                        <DropdownMenuItem
                            onClick={() => navigator.clipboard.writeText(document.id)}
                        >
                            ID kopieren
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem>Anzeigen</DropdownMenuItem>
                        <DropdownMenuItem>Bearbeiten</DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive">
                            Löschen
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            );
        },
    },
];

// Simple columns without selection
const simpleColumns: ColumnDef<Document>[] = columns.filter((col) => col.id !== 'select');

// ==================== Meta ====================

const meta: Meta<typeof EnterpriseDataTable> = {
    title: 'UI/DataTable',
    component: EnterpriseDataTable,
    parameters: {
        layout: 'padded',
        docs: {
            description: {
                component:
                    'Enterprise-ready Data Table mit Sortierung, Filterung, Paginierung und Export.',
            },
        },
    },
    tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof meta>;

// ==================== Stories ====================

export const Default: Story = {
    args: {
        columns: simpleColumns,
        data: sampleDocuments,
        searchColumn: 'name',
        searchPlaceholder: 'Dokumente suchen...',
    },
};

export const WithSelection: Story = {
    args: {
        columns: columns,
        data: sampleDocuments,
        searchColumn: 'name',
        enableRowSelection: true,
    },
};

export const Loading: Story = {
    args: {
        columns: simpleColumns,
        data: [],
        isLoading: true,
    },
};

export const Empty: Story = {
    args: {
        columns: simpleColumns,
        data: [],
    },
};

export const WithRowClick: Story = {
    args: {
        columns: simpleColumns,
        data: sampleDocuments,
        onRowClick: fn(),
    },
};

export const Compact: Story = {
    args: {
        columns: simpleColumns,
        data: sampleDocuments,
        compact: true,
        pageSize: 5,
    },
};

export const WithExport: Story = {
    args: {
        columns: simpleColumns,
        data: sampleDocuments,
        enableExport: true,
        onExport: fn(),
    },
};

export const WithGrouping: Story = {
    args: {
        columns: simpleColumns,
        data: sampleDocuments,
        enableGrouping: true,
    },
};

export const GlobalFilter: Story = {
    args: {
        columns: simpleColumns,
        data: sampleDocuments,
        globalFilter: true,
        searchPlaceholder: 'Globale Suche...',
    },
};

export const CustomPageSize: Story = {
    args: {
        columns: simpleColumns,
        data: sampleDocuments,
        pageSize: 5,
        pageSizeOptions: [5, 10, 15, 20],
    },
};

export const AllFeatures: Story = {
    args: {
        columns: columns,
        data: sampleDocuments,
        searchColumn: 'name',
        searchPlaceholder: 'Dokumente suchen...',
        enableRowSelection: true,
        enableColumnVisibility: true,
        enableExport: true,
        enableGrouping: true,
        enableColumnResizing: true,
        onRowClick: fn(),
        onExport: fn(),
    },
};

// ==================== Dark Mode ====================

export const DarkMode: Story = {
    args: {
        columns: simpleColumns,
        data: sampleDocuments.slice(0, 5),
        searchColumn: 'name',
    },
    parameters: {
        backgrounds: { default: 'dark' },
    },
    decorators: [
        (Story) => (
            <div className="dark">
                <Story />
            </div>
        ),
    ],
};
