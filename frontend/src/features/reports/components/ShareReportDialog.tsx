/**
 * ShareReportDialog Component
 *
 * Dialog zum Teilen eines Report-Templates mit anderen Benutzern.
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Share2,
    Users,
    Eye,
    Play,
    Edit,
    Trash2,
    Loader2,
    UserPlus,
    AlertCircle,
} from 'lucide-react';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/hooks/use-toast';
import { shareTemplate, reportKeys } from '../api';
import type { ReportShareCreate } from '../types';

// ==================== Types ====================

interface ShareReportDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    templateId: string;
    templateName: string;
}

// ==================== Permission Config ====================

const PERMISSIONS = [
    {
        key: 'can_view',
        label: 'Ansehen',
        icon: Eye,
        description: 'Report-Definition und Ergebnisse ansehen',
        default: true,
    },
    {
        key: 'can_execute',
        label: 'Ausführen',
        icon: Play,
        description: 'Report ausführen und neue Ergebnisse generieren',
        default: true,
    },
    {
        key: 'can_edit',
        label: 'Bearbeiten',
        icon: Edit,
        description: 'Report-Definition bearbeiten',
        default: false,
    },
    {
        key: 'can_delete',
        label: 'Löschen',
        icon: Trash2,
        description: 'Report-Template löschen',
        default: false,
    },
] as const;

type PermissionKey = typeof PERMISSIONS[number]['key'];

// ==================== Component ====================

export function ShareReportDialog({
    open,
    onOpenChange,
    templateId,
    templateName,
}: ShareReportDialogProps) {
    const { toast } = useToast();
    const queryClient = useQueryClient();

    // Form State
    const [userId, setUserId] = useState('');
    const [permissions, setPermissions] = useState<Record<PermissionKey, boolean>>({
        can_view: true,
        can_execute: true,
        can_edit: false,
        can_delete: false,
    });
    const [error, setError] = useState<string | null>(null);

    // Share Mutation
    const shareMutation = useMutation({
        mutationFn: (data: ReportShareCreate) => shareTemplate(templateId, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: reportKeys.all });
            toast({
                title: 'Report geteilt',
                description: `"${templateName}" wurde erfolgreich geteilt.`,
            });
            handleClose();
        },
        onError: (err) => {
            const message = err instanceof Error ? err.message : 'Unbekannter Fehler';
            setError(message);
        },
    });

    const handleClose = () => {
        setUserId('');
        setPermissions({
            can_view: true,
            can_execute: true,
            can_edit: false,
            can_delete: false,
        });
        setError(null);
        onOpenChange(false);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (!userId.trim()) {
            setError('Bitte geben Sie eine Benutzer-ID ein.');
            return;
        }

        // Validate UUID format
        const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        if (!uuidRegex.test(userId.trim())) {
            setError('Bitte geben Sie eine gültige Benutzer-ID (UUID) ein.');
            return;
        }

        shareMutation.mutate({
            user_id: userId.trim(),
            can_view: permissions.can_view,
            can_execute: permissions.can_execute,
            can_edit: permissions.can_edit,
            can_delete: permissions.can_delete,
        });
    };

    const togglePermission = (key: PermissionKey) => {
        setPermissions((prev) => ({
            ...prev,
            [key]: !prev[key],
        }));
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <form onSubmit={handleSubmit}>
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Share2 className="h-5 w-5" />
                            Report teilen
                        </DialogTitle>
                        <DialogDescription>
                            Teilen Sie "{templateName}" mit einem anderen Benutzer und legen Sie
                            fest, welche Berechtigungen er erhalten soll.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-6 py-4">
                        {/* Error Alert */}
                        {error && (
                            <Alert variant="destructive">
                                <AlertCircle className="h-4 w-4" />
                                <AlertDescription>{error}</AlertDescription>
                            </Alert>
                        )}

                        {/* User ID Input */}
                        <div className="space-y-2">
                            <Label htmlFor="userId" className="flex items-center gap-2">
                                <UserPlus className="h-4 w-4" />
                                Benutzer-ID
                            </Label>
                            <Input
                                id="userId"
                                value={userId}
                                onChange={(e) => setUserId(e.target.value)}
                                placeholder="z.B. 550e8400-e29b-41d4-a716-446655440000"
                                className="font-mono text-sm"
                            />
                            <p className="text-xs text-muted-foreground">
                                Die UUID des Benutzers, mit dem Sie teilen möchten.
                            </p>
                        </div>

                        <Separator />

                        {/* Permissions */}
                        <div className="space-y-4">
                            <Label className="flex items-center gap-2">
                                <Users className="h-4 w-4" />
                                Berechtigungen
                            </Label>

                            <TooltipProvider delayDuration={300}>
                                <div className="space-y-3">
                                    {PERMISSIONS.map((perm) => (
                                        <div
                                            key={perm.key}
                                            className="flex items-center justify-between py-2 px-3 rounded-lg border bg-muted/30"
                                        >
                                            <div className="flex items-center gap-3">
                                                <perm.icon className="h-4 w-4 text-muted-foreground" />
                                                <div>
                                                    <p className="text-sm font-medium">{perm.label}</p>
                                                    <Tooltip>
                                                        <TooltipTrigger asChild>
                                                            <p className="text-xs text-muted-foreground truncate max-w-[250px]">
                                                                {perm.description}
                                                            </p>
                                                        </TooltipTrigger>
                                                        <TooltipContent>
                                                            <p>{perm.description}</p>
                                                        </TooltipContent>
                                                    </Tooltip>
                                                </div>
                                            </div>
                                            <Switch
                                                checked={permissions[perm.key]}
                                                onCheckedChange={() => togglePermission(perm.key)}
                                            />
                                        </div>
                                    ))}
                                </div>
                            </TooltipProvider>
                        </div>
                    </div>

                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={handleClose}
                            disabled={shareMutation.isPending}
                        >
                            Abbrechen
                        </Button>
                        <Button type="submit" disabled={shareMutation.isPending}>
                            {shareMutation.isPending ? (
                                <>
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    Teilen...
                                </>
                            ) : (
                                <>
                                    <Share2 className="h-4 w-4 mr-2" />
                                    Teilen
                                </>
                            )}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

export default ShareReportDialog;
