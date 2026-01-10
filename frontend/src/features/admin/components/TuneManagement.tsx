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
    Plus, Pencil, Trash2, Loader2, Receipt, Scale, Mail, Wrench,
    FileText, Image, Book, Briefcase, CreditCard, DollarSign
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { Tune } from '@/features/upload/types';

// Type-safe icon mapping
const ICON_MAP: Record<string, LucideIcon> = {
    Receipt, Scale, Mail, Wrench, FileText, Image, Book, Briefcase, CreditCard, DollarSign
};

const AVAILABLE_COLORS = [
    { name: 'Emerald', value: 'bg-emerald-500' },
    { name: 'Blue', value: 'bg-blue-500' },
    { name: 'Amber', value: 'bg-amber-500' },
    { name: 'Slate', value: 'bg-slate-500' },
    { name: 'Red', value: 'bg-red-500' },
    { name: 'Purple', value: 'bg-purple-500' },
    { name: 'Pink', value: 'bg-pink-500' },
    { name: 'Indigo', value: 'bg-indigo-500' },
];

const AVAILABLE_ICONS = Object.keys(ICON_MAP);

export function TuneManagement() {
    const queryClient = useQueryClient();
    const { toast } = useToast();
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [editingTune, setEditingTune] = useState<Tune | null>(null);

    // Fetch Tunes
    const { data: tunes, isLoading } = useQuery({
        queryKey: ['tunes'],
        queryFn: async () => {
            const response = await apiClient.get('/tunes');
            return response.data as Tune[];
        }
    });

    // Create Mutation
    const createMutation = useMutation({
        mutationFn: async (data: Partial<Tune>) => {
            await apiClient.post('/tunes', data);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tunes'] });
            setIsDialogOpen(false);
            toast({
                title: 'Tune erstellt',
                description: 'Der neue Tune wurde erfolgreich erstellt.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Erstellen',
                description: error.message || 'Der Tune konnte nicht erstellt werden.',
                variant: 'destructive',
            });
        }
    });

    // Update Mutation
    const updateMutation = useMutation({
        mutationFn: async (data: Partial<Tune>) => {
            await apiClient.put(`/tunes/${data.id}`, data);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tunes'] });
            setIsDialogOpen(false);
            setEditingTune(null);
            toast({
                title: 'Tune aktualisiert',
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
        mutationFn: async (id: string) => {
            await apiClient.delete(`/tunes/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tunes'] });
            toast({
                title: 'Tune gelöscht',
                description: 'Der Tune wurde erfolgreich entfernt.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler beim Löschen',
                description: error.message || 'Der Tune konnte nicht gelöscht werden.',
                variant: 'destructive',
            });
        }
    });

    const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);

        const defaultBackend = formData.get('default_backend') as string;

        const data: Partial<Tune> = {
            name: formData.get('name') as string,
            description: formData.get('description') as string,
            icon: formData.get('icon') as string,
            color: formData.get('color') as string,
            prompt_template: formData.get('prompt_template') as string,
            default_backend: defaultBackend === 'auto' ? undefined : defaultBackend || undefined,
            is_active: formData.get('is_active') === 'on',
        };

        if (editingTune) {
            updateMutation.mutate({ ...data, id: editingTune.id });
        } else {
            createMutation.mutate(data);
        }
    };

    const openEdit = (tune: Tune) => {
        setEditingTune(tune);
        setIsDialogOpen(true);
    };

    const openCreate = () => {
        setEditingTune(null);
        setIsDialogOpen(true);
    };

    if (isLoading) return <div className="flex justify-center p-8"><Loader2 className="animate-spin" /></div>;

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Tune Konfiguration</h1>
                    <p className="text-muted-foreground">Verwalten Sie Dokumenten-Kontexte und Analyse-Einstellungen.</p>
                </div>
                <Button onClick={openCreate}><Plus className="mr-2 h-4 w-4" /> Neuer Tune</Button>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {tunes?.map(tune => {
                    // Type-safe dynamic Icon Component
                    const IconComponent = ICON_MAP[tune.icon] || FileText;

                    return (
                        <Card key={tune.id} className="relative overflow-hidden">
                            <div className={`absolute top-0 left-0 w-1 h-full ${tune.color}`} />
                            <CardHeader className="pb-2">
                                <div className="flex justify-between items-start">
                                    <div className="flex items-center gap-2">
                                        <div className={`p-2 rounded-lg ${tune.color} bg-opacity-10`}>
                                            <IconComponent className={`h-5 w-5 ${tune.color.replace('bg-', 'text-')}`} />
                                        </div>
                                        <CardTitle className="text-lg">{tune.name}</CardTitle>
                                    </div>
                                    {tune.is_system && <Badge variant="secondary">System</Badge>}
                                </div>
                                <CardDescription className="line-clamp-2 min-h-[2.5rem]">
                                    {tune.description}
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="flex justify-between items-center mt-4">
                                    <div className="flex gap-2">
                                        <Badge variant="outline">{tune.default_backend || 'Auto'}</Badge>
                                        {!tune.is_active && <Badge variant="destructive">Inaktiv</Badge>}
                                    </div>
                                    <div className="flex gap-2">
                                        <Button variant="ghost" size="icon" onClick={() => openEdit(tune)}>
                                            <Pencil className="h-4 w-4" />
                                        </Button>
                                        {!tune.is_system && (
                                            <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" onClick={() => deleteMutation.mutate(tune.id)}>
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

            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                <DialogContent className="max-w-2xl">
                    <DialogHeader>
                        <DialogTitle>{editingTune ? 'Tune bearbeiten' : 'Neuer Tune'}</DialogTitle>
                    </DialogHeader>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="name">Name</Label>
                                <Input id="name" name="name" defaultValue={editingTune?.name} required />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="icon">Icon</Label>
                                <Select name="icon" defaultValue={editingTune?.icon || 'FileText'}>
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
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="description">Beschreibung</Label>
                            <Textarea id="description" name="description" defaultValue={editingTune?.description ?? ''} />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label htmlFor="color">Farbe</Label>
                                <Select name="color" defaultValue={editingTune?.color || 'bg-slate-500'}>
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
                            <div className="space-y-2">
                                <Label htmlFor="default_backend">Standard OCR Backend</Label>
                                <Select name="default_backend" defaultValue={editingTune?.default_backend || 'auto'}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Automatisch" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="auto">Automatisch</SelectItem>
                                        <SelectItem value="deepseek">DeepSeek</SelectItem>
                                        <SelectItem value="got_ocr">GOT-OCR</SelectItem>
                                        <SelectItem value="surya">Surya</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="prompt_template">System Prompt Template (Optional)</Label>
                            <Textarea
                                id="prompt_template"
                                name="prompt_template"
                                defaultValue={editingTune?.prompt_template ?? ''}
                                placeholder="Spezifische Anweisungen für die KI-Analyse..."
                                className="font-mono text-sm h-32"
                            />
                        </div>

                        <div className="flex items-center space-x-2">
                            <Checkbox id="is_active" name="is_active" defaultChecked={editingTune?.is_active ?? true} />
                            <Label htmlFor="is_active">Aktiv</Label>
                        </div>

                        <DialogFooter>
                            <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>Abbrechen</Button>
                            <Button type="submit">Speichern</Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>
        </div>
    );
}
