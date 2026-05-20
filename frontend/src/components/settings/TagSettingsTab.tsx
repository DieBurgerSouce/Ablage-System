/**
 * Tag Settings Tab Komponente.
 *
 * Admin-Tab für die Verwaltung von Dokument-Tags.
 * Erlaubt CRUD-Operationen und Tune-Verknüpfung.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '@/components/ui/dialog';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useToast } from '@/components/ui/use-toast';
import {
    Plus, Pencil, Trash2, Loader2, Tag as TagIcon,
    ArrowDownLeft, ArrowUpRight, FileText, Folder, Receipt,
    CircleDollarSign, FileCheck, Users, Building2, Briefcase
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { settingsService } from '@/lib/api/services/settings';
import { apiClient } from '@/lib/api/client';
import type { Tag, TagCreate, Tune } from '@/features/upload/types';

// Type-safe icon mapping
const ICON_MAP: Record<string, LucideIcon> = {
    Tag: TagIcon,
    ArrowDownLeft,
    ArrowUpRight,
    FileText,
    Folder,
    Receipt,
    CircleDollarSign,
    FileCheck,
    Users,
    Building2,
    Briefcase
};

const AVAILABLE_COLORS = [
    { name: 'Grün', value: 'bg-green-500' },
    { name: 'Blau', value: 'bg-blue-500' },
    { name: 'Gelb', value: 'bg-amber-500' },
    { name: 'Grau', value: 'bg-slate-500' },
    { name: 'Rot', value: 'bg-red-500' },
    { name: 'Lila', value: 'bg-purple-500' },
    { name: 'Pink', value: 'bg-pink-500' },
    { name: 'Indigo', value: 'bg-indigo-500' },
    { name: 'Türkis', value: 'bg-cyan-500' },
    { name: 'Orange', value: 'bg-orange-500' },
];

const AVAILABLE_ICONS = Object.keys(ICON_MAP);

export function TagSettingsTab() {
    const queryClient = useQueryClient();
    const { toast } = useToast();
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [editingTag, setEditingTag] = useState<Tag | null>(null);

    // Fetch Tags
    const { data: tags, isLoading: isLoadingTags } = useQuery({
        queryKey: ['admin-tags'],
        queryFn: () => settingsService.getTags()
    });

    // Fetch Tunes for linking
    const { data: tunes } = useQuery({
        queryKey: ['tunes'],
        queryFn: async () => {
            const response = await apiClient.get<Tune[]>('/tunes');
            return response.data;
        }
    });

    // Create Mutation
    const createMutation = useMutation({
        mutationFn: (data: TagCreate) => settingsService.createTag(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-tags'] });
            setIsDialogOpen(false);
            toast({
                title: 'Tag erstellt',
                description: 'Der neue Tag wurde erfolgreich erstellt.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Erstellen',
                description: error.message || 'Das Tag konnte nicht erstellt werden.',
                variant: 'destructive',
            });
        }
    });

    // Update Mutation
    const updateMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: TagCreate }) =>
            settingsService.updateTag(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-tags'] });
            setIsDialogOpen(false);
            setEditingTag(null);
            toast({
                title: 'Tag aktualisiert',
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

    // Delete Mutation
    const deleteMutation = useMutation({
        mutationFn: (id: string) => settingsService.deleteTag(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin-tags'] });
            toast({
                title: 'Tag gelöscht',
                description: 'Das Tag wurde erfolgreich entfernt.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Löschen',
                description: error.message || 'Das Tag konnte nicht gelöscht werden.',
                variant: 'destructive',
            });
        }
    });

    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);

        const tuneId = formData.get('tune_id') as string;

        const data: TagCreate = {
            name: formData.get('name') as string,
            description: (formData.get('description') as string) || undefined,
            icon: formData.get('icon') as string,
            color: formData.get('color') as string,
            tune_id: tuneId && tuneId !== 'none' ? tuneId : undefined,
            is_active: formData.get('is_active') === 'on',
        };

        if (editingTag) {
            updateMutation.mutate({ id: editingTag.id, data });
        } else {
            createMutation.mutate(data);
        }
    };

    const openEdit = (tag: Tag) => {
        setEditingTag(tag);
        setIsDialogOpen(true);
    };

    const openCreate = () => {
        setEditingTag(null);
        setIsDialogOpen(true);
    };

    const handleDelete = (tag: Tag) => {
        if (tag.is_system) {
            toast({
                title: 'Löschen nicht möglich',
                description: 'System-Tags können nicht gelöscht werden.',
                variant: 'destructive',
            });
            return;
        }
        deleteMutation.mutate(tag.id);
    };

    // Find linked tune name
    const getTuneName = (tuneId: string | null): string | null => {
        if (!tuneId || !tunes) return null;
        const tune = tunes.find(t => t.id === tuneId);
        return tune?.name || null;
    };

    if (isLoadingTags) {
        return (
            <div className="flex justify-center items-center p-8">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-start">
                <div>
                    <h3 className="text-lg font-medium">Tag-Verwaltung</h3>
                    <p className="text-sm text-muted-foreground">
                        Verwalten Sie Tags für die Dokumentenkategorisierung.
                        Tags können optional mit Tunes verknüpft werden.
                    </p>
                </div>
                <Button onClick={openCreate} size="sm">
                    <Plus className="mr-2 h-4 w-4" />
                    Neuer Tag
                </Button>
            </div>

            {/* Tags Grid */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {tags?.map(tag => {
                    const IconComponent = ICON_MAP[tag.icon] || TagIcon;
                    const linkedTuneName = getTuneName(tag.tune_id);

                    return (
                        <Card key={tag.id} className="relative overflow-hidden">
                            <div className={`absolute top-0 left-0 w-1 h-full ${tag.color || 'bg-slate-500'}`} />
                            <CardHeader className="pb-2">
                                <div className="flex justify-between items-start">
                                    <div className="flex items-center gap-2">
                                        <div className={`p-2 rounded-lg ${tag.color || 'bg-slate-500'} bg-opacity-10`}>
                                            <IconComponent className={`h-5 w-5 ${(tag.color || 'bg-slate-500').replace('bg-', 'text-')}`} />
                                        </div>
                                        <CardTitle className="text-lg">{tag.name}</CardTitle>
                                    </div>
                                    <div className="flex gap-1">
                                        {!tag.is_active && <Badge variant="destructive">Inaktiv</Badge>}
                                    </div>
                                </div>
                                <CardDescription className="line-clamp-2 min-h-[2.5rem]">
                                    {tag.description || 'Keine Beschreibung'}
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="flex justify-between items-center mt-2">
                                    <div className="flex gap-2">
                                        {linkedTuneName && (
                                            <Badge variant="outline" className="text-xs">
                                                Tune: {linkedTuneName}
                                            </Badge>
                                        )}
                                    </div>
                                    <div className="flex gap-1">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => openEdit(tag)}
                                        >
                                            <Pencil className="h-4 w-4" />
                                        </Button>
                                        {!tag.is_system && (
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="text-destructive hover:text-destructive"
                                                onClick={() => handleDelete(tag)}
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    );
                })}
            </div>

            {/* Empty State */}
            {tags?.length === 0 && (
                <div className="text-center py-12 text-muted-foreground">
                    <TagIcon className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>Keine Tags vorhanden.</p>
                    <p className="text-sm">Erstellen Sie einen neuen Tag um zu beginnen.</p>
                </div>
            )}

            {/* Create/Edit Dialog */}
            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>
                            {editingTag ? 'Tag bearbeiten' : 'Neuen Tag erstellen'}
                        </DialogTitle>
                    </DialogHeader>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="name">Name *</Label>
                            <Input
                                id="name"
                                name="name"
                                defaultValue={editingTag?.name}
                                required
                                maxLength={50}
                                placeholder="z.B. Eingangsrechnung"
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="description">Beschreibung</Label>
                            <Textarea
                                id="description"
                                name="description"
                                defaultValue={editingTag?.description ?? ''}
                                maxLength={255}
                                placeholder="Optionale Beschreibung des Tags"
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="icon">Icon</Label>
                                <Select name="icon" defaultValue={editingTag?.icon || 'Tag'}>
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {AVAILABLE_ICONS.map(iconName => {
                                            const IconComp = ICON_MAP[iconName];
                                            return (
                                                <SelectItem key={iconName} value={iconName}>
                                                    <div className="flex items-center gap-2">
                                                        {IconComp && <IconComp className="h-4 w-4" />}
                                                        {iconName}
                                                    </div>
                                                </SelectItem>
                                            );
                                        })}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="color">Farbe</Label>
                                <Select name="color" defaultValue={editingTag?.color || 'bg-slate-500'}>
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {AVAILABLE_COLORS.map(color => (
                                            <SelectItem key={color.value} value={color.value}>
                                                <div className="flex items-center gap-2">
                                                    <div className={`w-4 h-4 rounded-full ${color.value}`} />
                                                    {color.name}
                                                </div>
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="tune_id">Verknüpfter Tune (Optional)</Label>
                            <Select
                                name="tune_id"
                                defaultValue={editingTag?.tune_id || 'none'}
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder="Kein Tune" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="none">Kein Tune</SelectItem>
                                    {tunes?.filter(t => t.is_active).map(tune => (
                                        <SelectItem key={tune.id} value={tune.id}>
                                            {tune.name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <p className="text-xs text-muted-foreground">
                                Verknüpft dieses Tag mit einem Tune für OCR-Feintuning.
                            </p>
                        </div>

                        <div className="flex items-center space-x-2">
                            <Checkbox
                                id="is_active"
                                name="is_active"
                                defaultChecked={editingTag?.is_active ?? true}
                            />
                            <Label htmlFor="is_active">Aktiv</Label>
                        </div>

                        <DialogFooter>
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => setIsDialogOpen(false)}
                            >
                                Abbrechen
                            </Button>
                            <Button
                                type="submit"
                                disabled={createMutation.isPending || updateMutation.isPending}
                            >
                                {(createMutation.isPending || updateMutation.isPending) && (
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                )}
                                Speichern
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>
        </div>
    );
}
