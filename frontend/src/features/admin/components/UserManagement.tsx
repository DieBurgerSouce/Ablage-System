import { useState } from 'react';
import {
    useReactTable,
    getCoreRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    flexRender,
    createColumnHelper,
    SortingState
} from '@tanstack/react-table';
import { MoreHorizontal, Plus, Shield, ShieldAlert, ShieldCheck, Trash2, Edit2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

// Mock Data & Types
interface User {
    id: string;
    name: string;
    email: string;
    role: 'admin' | 'editor' | 'viewer';
    lastLogin: string;
    status: 'active' | 'inactive';
}

const mockUsers: User[] = [
    { id: '1', name: 'Admin User', email: 'admin@company.com', role: 'admin', lastLogin: '2023-11-28T10:30:00', status: 'active' },
    { id: '2', name: 'Max Mustermann', email: 'max@company.com', role: 'editor', lastLogin: '2023-11-29T14:15:00', status: 'active' },
    { id: '3', name: 'Lisa Schmidt', email: 'lisa@company.com', role: 'viewer', lastLogin: '2023-11-25T09:00:00', status: 'inactive' },
];

// RBAC Hook (Mocked)
function usePermissions() {
    // In a real app, this would come from auth context
    const currentUserRole = 'admin';

    const can = (action: string, resource: string) => {
        if (currentUserRole === 'admin') return true;
        if (currentUserRole === 'editor' && action !== 'delete') return true;
        return false;
    };

    return { can };
}

const columnHelper = createColumnHelper<User>();

export function UserManagement() {
    const [data] = useState(mockUsers);
    const [sorting, setSorting] = useState<SortingState>([]);
    const { can } = usePermissions();

    const columns = [
        columnHelper.accessor('name', {
            header: 'Name',
            cell: info => <span className="font-medium">{info.getValue()}</span>
        }),
        columnHelper.accessor('email', {
            header: 'E-Mail',
        }),
        columnHelper.accessor('role', {
            header: 'Rolle',
            cell: info => {
                const role = info.getValue();
                return (
                    <Badge variant={role === 'admin' ? 'default' : role === 'editor' ? 'secondary' : 'outline'} className="gap-1">
                        {role === 'admin' && <ShieldAlert className="w-3 h-3" />}
                        {role === 'editor' && <ShieldCheck className="w-3 h-3" />}
                        {role === 'viewer' && <Shield className="w-3 h-3" />}
                        {role.charAt(0).toUpperCase() + role.slice(1)}
                    </Badge>
                );
            }
        }),
        columnHelper.accessor('status', {
            header: 'Status',
            cell: info => (
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${info.getValue() === 'active' ? 'bg-green-500' : 'bg-gray-300'}`} />
                    <span className="text-sm text-muted-foreground capitalize">{info.getValue()}</span>
                </div>
            )
        }),
        columnHelper.display({
            id: 'actions',
            cell: ({ row }) => can('edit', 'users') && (
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8 p-0">
                            <MoreHorizontal className="h-4 w-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => console.log('Edit', row.original)}>
                            <Edit2 className="mr-2 h-4 w-4" /> Bearbeiten
                        </DropdownMenuItem>
                        {can('delete', 'users') && (
                            <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => console.log('Delete', row.original)}>
                                <Trash2 className="mr-2 h-4 w-4" /> Löschen
                            </DropdownMenuItem>
                        )}
                    </DropdownMenuContent>
                </DropdownMenu>
            )
        })
    ];

    const table = useReactTable({
        data,
        columns,
        state: { sorting },
        onSortingChange: setSorting,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getPaginationRowModel: getPaginationRowModel(),
    });

    return (
        <Card className="w-full max-w-5xl mx-auto">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
                <div>
                    <CardTitle className="text-2xl font-display">Benutzerverwaltung</CardTitle>
                    <p className="text-sm text-muted-foreground mt-1">Verwalten Sie Zugriffsrechte und Rollen.</p>
                </div>
                {can('create', 'users') && (
                    <Button>
                        <Plus className="mr-2 h-4 w-4" /> Benutzer hinzufügen
                    </Button>
                )}
            </CardHeader>
            <CardContent>
                <div className="rounded-md border">
                    <Table>
                        <TableHeader>
                            {table.getHeaderGroups().map(headerGroup => (
                                <TableRow key={headerGroup.id}>
                                    {headerGroup.headers.map(header => (
                                        <TableHead key={header.id}>
                                            {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                                        </TableHead>
                                    ))}
                                </TableRow>
                            ))}
                        </TableHeader>
                        <TableBody>
                            {table.getRowModel().rows?.length ? (
                                table.getRowModel().rows.map(row => (
                                    <TableRow key={row.id} data-state={row.getIsSelected() && "selected"}>
                                        {row.getVisibleCells().map(cell => (
                                            <TableCell key={cell.id}>
                                                {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                            </TableCell>
                                        ))}
                                    </TableRow>
                                ))
                            ) : (
                                <TableRow>
                                    <TableCell colSpan={columns.length} className="h-24 text-center">
                                        Keine Ergebnisse.
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </div>
                <div className="flex items-center justify-end space-x-2 py-4">
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
            </CardContent>
        </Card>
    );
}
