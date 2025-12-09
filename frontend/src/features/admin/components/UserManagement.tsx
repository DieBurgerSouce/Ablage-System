import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription
} from '@/components/ui/dialog';
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import {
    MoreHorizontal, Plus, Search, Shield, User as UserIcon, Lock, Ban, CheckCircle, Trash2, RefreshCw
} from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import { cn } from '@/lib/utils';

interface User {
    id: string;
    email: string;
    username: string;
    full_name?: string;
    is_active: boolean;
    is_superuser: boolean;
    tier: 'free' | 'premium' | 'admin';
    daily_quota: number;
    documents_processed_today: number;
    created_at: string;
    last_login?: string;
}

interface UserListResponse {
    items: User[];
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
}

interface CreateUserData {
    username: string;
    email: string;
    full_name?: string;
    password: string;
    tier: 'free' | 'premium' | 'admin';
    daily_quota: number;
    is_superuser: boolean;
    is_active: boolean;
}

interface UpdateUserData extends Omit<CreateUserData, 'password'> {
    id: string;
}

export function UserManagement() {
    const queryClient = useQueryClient();
    const { toast } = useToast();
    const [page, setPage] = useState(1);
    const [search, setSearch] = useState('');
    const [roleFilter, setRoleFilter] = useState<string>('all');
    const [statusFilter, setStatusFilter] = useState<string>('all');

    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [editingUser, setEditingUser] = useState<User | null>(null);
    const [isPasswordResetOpen, setIsPasswordResetOpen] = useState(false);
    const [tempPassword, setTempPassword] = useState<string | null>(null);

    // Fetch Users
    const { data, isLoading } = useQuery({
        queryKey: ['users', page, search, roleFilter, statusFilter],
        queryFn: async () => {
            const params = new URLSearchParams({
                page: page.toString(),
                per_page: '20',
            });
            if (search) params.append('search', search);
            if (roleFilter !== 'all') params.append('role', roleFilter);
            if (statusFilter !== 'all') params.append('status', statusFilter);

            const response = await apiClient.get(`/api/v1/admin/users?${params.toString()}`);
            return response.data as UserListResponse;
        }
    });

    // Mutations
    const createMutation = useMutation({
        mutationFn: async (data: CreateUserData) => {
            await apiClient.post('/api/v1/admin/users', data);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            setIsDialogOpen(false);
            toast({
                title: 'Benutzer erstellt',
                description: 'Der neue Benutzer wurde erfolgreich erstellt.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Erstellen',
                description: error.message || 'Der Benutzer konnte nicht erstellt werden.',
                variant: 'destructive',
            });
        }
    });

    const updateMutation = useMutation({
        mutationFn: async (data: UpdateUserData) => {
            await apiClient.patch(`/api/v1/admin/users/${data.id}`, data);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            setIsDialogOpen(false);
            setEditingUser(null);
            toast({
                title: 'Benutzer aktualisiert',
                description: 'Die Änderungen wurden erfolgreich gespeichert.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Aktualisieren',
                description: error.message || 'Die Änderungen konnten nicht gespeichert werden.',
                variant: 'destructive',
            });
        }
    });

    const deleteMutation = useMutation({
        mutationFn: async (id: string) => {
            if (!confirm('Sind Sie sicher? Dieser Benutzer wird dauerhaft gelöscht.')) return;
            await apiClient.delete(`/api/v1/admin/users/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            toast({
                title: 'Benutzer gelöscht',
                description: 'Der Benutzer wurde erfolgreich entfernt.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Löschen',
                description: error.message || 'Der Benutzer konnte nicht gelöscht werden.',
                variant: 'destructive',
            });
        }
    });

    const toggleStatusMutation = useMutation({
        mutationFn: async (user: User) => {
            const action = user.is_active ? 'deactivate' : 'activate';
            await apiClient.post(`/api/v1/admin/users/${user.id}/${action}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['users'] });
            toast({
                title: 'Status geändert',
                description: 'Der Benutzerstatus wurde erfolgreich geändert.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Statusändern',
                description: error.message || 'Der Status konnte nicht geändert werden.',
                variant: 'destructive',
            });
        }
    });

    const resetPasswordMutation = useMutation({
        mutationFn: async (id: string) => {
            const response = await apiClient.post(`/api/v1/admin/users/${id}/reset-password`);
            return response.data.temp_password as string;
        },
        onSuccess: (password) => {
            setTempPassword(password);
            setIsPasswordResetOpen(true);
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Passwort-Reset',
                description: error.message || 'Das Passwort konnte nicht zurückgesetzt werden.',
                variant: 'destructive',
            });
        }
    });

    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);

        const baseData = {
            username: formData.get('username') as string,
            email: formData.get('email') as string,
            full_name: formData.get('full_name') as string || undefined,
            tier: formData.get('tier') as 'free' | 'premium' | 'admin',
            daily_quota: parseInt(formData.get('daily_quota') as string),
            is_superuser: formData.get('is_superuser') === 'on',
            is_active: formData.get('is_active') === 'on',
        };

        if (editingUser) {
            updateMutation.mutate({ ...baseData, id: editingUser.id });
        } else {
            createMutation.mutate({
                ...baseData,
                password: formData.get('password') as string,
            });
        }
    };

    const openCreate = () => {
        setEditingUser(null);
        setIsDialogOpen(true);
    };

    const openEdit = (user: User) => {
        setEditingUser(user);
        setIsDialogOpen(true);
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Benutzerverwaltung</h2>
                    <p className="text-muted-foreground">Verwalten Sie Benutzer, Rollen und Berechtigungen.</p>
                </div>
                <Button onClick={openCreate}><Plus className="mr-2 h-4 w-4" /> Neuer Benutzer</Button>
            </div>

            {/* Filters */}
            <div className="flex gap-4 items-center bg-card p-4 rounded-lg border">
                <div className="relative flex-1 max-w-sm">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Suche nach Name oder E-Mail..."
                        className="pl-9"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>
                <Select value={roleFilter} onValueChange={setRoleFilter}>
                    <SelectTrigger className="w-[180px]">
                        <SelectValue placeholder="Rolle" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Alle Rollen</SelectItem>
                        <SelectItem value="superuser">Administrator</SelectItem>
                        <SelectItem value="user">Benutzer</SelectItem>
                    </SelectContent>
                </Select>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                    <SelectTrigger className="w-[180px]">
                        <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Alle Status</SelectItem>
                        <SelectItem value="active">Aktiv</SelectItem>
                        <SelectItem value="inactive">Inaktiv</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Table */}
            <div className="rounded-md border bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Benutzer</TableHead>
                            <TableHead>Rolle</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Tier</TableHead>
                            <TableHead>Quota (Heute)</TableHead>
                            <TableHead className="text-right">Aktionen</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {isLoading ? (
                            <TableRow>
                                <TableCell colSpan={6} className="text-center h-24">Laden...</TableCell>
                            </TableRow>
                        ) : data?.items.map((user) => (
                            <TableRow key={user.id}>
                                <TableCell>
                                    <div className="flex items-center gap-3">
                                        <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-medium">
                                            {user.username.substring(0, 2).toUpperCase()}
                                        </div>
                                        <div>
                                            <div className="font-medium">{user.full_name || user.username}</div>
                                            <div className="text-xs text-muted-foreground">{user.email}</div>
                                        </div>
                                    </div>
                                </TableCell>
                                <TableCell>
                                    {user.is_superuser ? (
                                        <Badge variant="destructive" className="gap-1"><Shield className="w-3 h-3" /> Admin</Badge>
                                    ) : (
                                        <Badge variant="secondary" className="gap-1"><UserIcon className="w-3 h-3" /> User</Badge>
                                    )}
                                </TableCell>
                                <TableCell>
                                    {user.is_active ? (
                                        <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 gap-1">
                                            <CheckCircle className="w-3 h-3" /> Aktiv
                                        </Badge>
                                    ) : (
                                        <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 gap-1">
                                            <Ban className="w-3 h-3" /> Inaktiv
                                        </Badge>
                                    )}
                                </TableCell>
                                <TableCell>
                                    <Badge variant="outline" className={cn(
                                        user.tier === 'premium' && "border-amber-400 text-amber-600 bg-amber-50",
                                        user.tier === 'admin' && "border-purple-400 text-purple-600 bg-purple-50"
                                    )}>
                                        {user.tier.toUpperCase()}
                                    </Badge>
                                </TableCell>
                                <TableCell>
                                    <div className="flex flex-col gap-1 w-32">
                                        <div className="flex justify-between text-xs">
                                            <span>{user.documents_processed_today} / {user.daily_quota}</span>
                                            <span className="text-muted-foreground">
                                                {Math.round((user.documents_processed_today / user.daily_quota) * 100)}%
                                            </span>
                                        </div>
                                        <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-primary transition-all"
                                                style={{ width: `${Math.min(100, (user.documents_processed_today / user.daily_quota) * 100)}%` }}
                                            />
                                        </div>
                                    </div>
                                </TableCell>
                                <TableCell className="text-right">
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" size="icon"><MoreHorizontal className="w-4 h-4" /></Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuLabel>Aktionen</DropdownMenuLabel>
                                            <DropdownMenuItem onClick={() => openEdit(user)}>
                                                <RefreshCw className="w-4 h-4 mr-2" /> Bearbeiten
                                            </DropdownMenuItem>
                                            <DropdownMenuItem onClick={() => resetPasswordMutation.mutate(user.id)}>
                                                <Lock className="w-4 h-4 mr-2" /> Passwort zurücksetzen
                                            </DropdownMenuItem>
                                            <DropdownMenuSeparator />
                                            <DropdownMenuItem onClick={() => toggleStatusMutation.mutate(user)}>
                                                {user.is_active ? (
                                                    <><Ban className="w-4 h-4 mr-2 text-red-500" /> Deaktivieren</>
                                                ) : (
                                                    <><CheckCircle className="w-4 h-4 mr-2 text-green-500" /> Aktivieren</>
                                                )}
                                            </DropdownMenuItem>
                                            <DropdownMenuItem
                                                className="text-destructive focus:text-destructive"
                                                onClick={() => deleteMutation.mutate(user.id)}
                                            >
                                                <Trash2 className="w-4 h-4 mr-2" /> Löschen
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-end space-x-2 py-4">
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((old) => Math.max(old - 1, 1))}
                    disabled={page === 1 || isLoading}
                >
                    Zurück
                </Button>
                <div className="text-sm text-muted-foreground">
                    Seite {page} von {data?.total_pages || 1}
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((old) => (data?.total_pages && old < data.total_pages ? old + 1 : old))}
                    disabled={page === (data?.total_pages || 1) || isLoading}
                >
                    Weiter
                </Button>
            </div>

            {/* Create/Edit Dialog */}
            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                <DialogContent className="max-w-2xl">
                    <DialogHeader>
                        <DialogTitle>{editingUser ? 'Benutzer bearbeiten' : 'Neuer Benutzer'}</DialogTitle>
                        <DialogDescription>
                            Verwalten Sie die Stammdaten und Berechtigungen des Benutzers.
                        </DialogDescription>
                    </DialogHeader>

                    <form onSubmit={handleSubmit}>
                        <Tabs defaultValue="base" className="w-full">
                            <TabsList className="grid w-full grid-cols-3">
                                <TabsTrigger value="base">Basisdaten</TabsTrigger>
                                <TabsTrigger value="permissions">Berechtigungen</TabsTrigger>
                                <TabsTrigger value="quotas">Quotas & Limits</TabsTrigger>
                            </TabsList>

                            <div className="py-4">
                                <TabsContent value="base" className="space-y-4">
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <Label htmlFor="username">Benutzername</Label>
                                            <Input id="username" name="username" defaultValue={editingUser?.username} required />
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="email">E-Mail</Label>
                                            <Input id="email" name="email" type="email" defaultValue={editingUser?.email} required />
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="full_name">Vollständiger Name</Label>
                                        <Input id="full_name" name="full_name" defaultValue={editingUser?.full_name} />
                                    </div>
                                    {!editingUser && (
                                        <div className="space-y-2">
                                            <Label htmlFor="password">Initial-Passwort</Label>
                                            <Input id="password" name="password" type="password" required minLength={8} />
                                        </div>
                                    )}
                                </TabsContent>

                                <TabsContent value="permissions" className="space-y-6">
                                    <div className="flex items-center justify-between space-x-2 border p-4 rounded-lg">
                                        <div className="space-y-0.5">
                                            <Label className="text-base">Administrator-Rechte</Label>
                                            <p className="text-sm text-muted-foreground">
                                                Gewährt vollen Zugriff auf alle Systemeinstellungen.
                                            </p>
                                        </div>
                                        <Checkbox id="is_superuser" name="is_superuser" defaultChecked={editingUser?.is_superuser} />
                                    </div>
                                    <div className="flex items-center justify-between space-x-2 border p-4 rounded-lg">
                                        <div className="space-y-0.5">
                                            <Label className="text-base">Konto Aktiv</Label>
                                            <p className="text-sm text-muted-foreground">
                                                Deaktivierte Benutzer können sich nicht anmelden.
                                            </p>
                                        </div>
                                        <Checkbox id="is_active" name="is_active" defaultChecked={editingUser?.is_active ?? true} />
                                    </div>
                                </TabsContent>

                                <TabsContent value="quotas" className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="tier">Abonnement-Tier</Label>
                                        <Select name="tier" defaultValue={editingUser?.tier || 'free'}>
                                            <SelectTrigger>
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="free">Free</SelectItem>
                                                <SelectItem value="premium">Premium</SelectItem>
                                                <SelectItem value="admin">Admin (Unlimited)</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="daily_quota">Tägliches Dokumentenlimit</Label>
                                        <Input
                                            id="daily_quota"
                                            name="daily_quota"
                                            type="number"
                                            defaultValue={editingUser?.daily_quota || 100}
                                        />
                                        <p className="text-xs text-muted-foreground">
                                            Überschreibt den Standardwert des Tiers.
                                        </p>
                                    </div>
                                </TabsContent>
                            </div>
                        </Tabs>

                        <DialogFooter>
                            <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>Abbrechen</Button>
                            <Button type="submit">Speichern</Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>

            {/* Password Reset Dialog */}
            <Dialog open={isPasswordResetOpen} onOpenChange={setIsPasswordResetOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Passwort zurückgesetzt</DialogTitle>
                        <DialogDescription>
                            Das Passwort wurde erfolgreich zurückgesetzt. Bitte teilen Sie dem Benutzer das folgende temporäre Passwort mit.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="p-4 bg-muted rounded-lg text-center font-mono text-xl tracking-wider select-all">
                        {tempPassword}
                    </div>
                    <DialogFooter>
                        <Button onClick={() => setIsPasswordResetOpen(false)}>Schließen</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
