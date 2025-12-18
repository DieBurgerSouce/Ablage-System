/**
 * Dialog zum Teilen einer Chat-Session mit anderen Benutzern.
 *
 * Features:
 * - User-Suche
 * - Access Level Auswahl
 * - Collaborator-Liste
 * - Zugriff entfernen
 */

import { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    Share2,
    Users,
    Loader2,
    Crown,
    Eye,
    Edit,
    Settings,
    UserMinus,
    Search,
    UserPlus,
} from 'lucide-react';
import { chatApi, type ChatAccessLevel } from '@/lib/api/chat-api';
import { adminService } from '@/lib/api/services/admin';
import { useToast } from '@/components/ui/use-toast';
import { cn } from '@/lib/utils';

// ============================================================================
// TYPES
// ============================================================================

interface ShareChatDialogProps {
    /** Session ID zum Teilen */
    sessionId: string | null;
    /** Dialog offen */
    open: boolean;
    /** Open-State aendern */
    onOpenChange: (open: boolean) => void;
    /** Session-Titel fuer Anzeige */
    sessionTitle?: string;
}

// ============================================================================
// HELPERS
// ============================================================================

function getAccessLevelIcon(level: ChatAccessLevel) {
    switch (level) {
        case 'owner':
            return <Crown className="h-4 w-4 text-amber-500" />;
        case 'manage':
            return <Settings className="h-4 w-4 text-blue-500" />;
        case 'contribute':
            return <Edit className="h-4 w-4 text-green-500" />;
        case 'view':
            return <Eye className="h-4 w-4 text-gray-500" />;
        default:
            return null;
    }
}

function getAccessLevelLabel(level: ChatAccessLevel): string {
    switch (level) {
        case 'owner':
            return 'Besitzer';
        case 'manage':
            return 'Verwalten';
        case 'contribute':
            return 'Mitarbeiten';
        case 'view':
            return 'Ansehen';
        default:
            return level;
    }
}

function getAccessLevelDescription(level: string): string {
    switch (level) {
        case 'manage':
            return 'Kann andere einladen und entfernen';
        case 'contribute':
            return 'Kann Nachrichten senden';
        case 'view':
            return 'Kann nur lesen';
        default:
            return '';
    }
}

// ============================================================================
// COMPONENT
// ============================================================================

export function ShareChatDialog({
    sessionId,
    open,
    onOpenChange,
    sessionTitle,
}: ShareChatDialogProps) {
    const { toast } = useToast();
    const queryClient = useQueryClient();

    // State
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
    const [selectedAccessLevel, setSelectedAccessLevel] = useState<'view' | 'contribute' | 'manage'>('view');

    // Reset state when dialog opens
    useEffect(() => {
        if (open) {
            setSearchQuery('');
            setSelectedUserId(null);
            setSelectedAccessLevel('view');
        }
    }, [open]);

    // Queries
    const { data: collaborators = [], isLoading: loadingCollaborators } = useQuery({
        queryKey: ['chat-collaborators', sessionId],
        queryFn: () => (sessionId ? chatApi.getCollaborators(sessionId) : []),
        enabled: !!sessionId && open,
    });

    const { data: users = [], isLoading: loadingUsers } = useQuery({
        queryKey: ['admin-users'],
        queryFn: () => adminService.getUsers(),
        enabled: open,
    });

    // Mutations
    const shareMutation = useMutation({
        mutationFn: ({
            userId,
            accessLevel,
        }: {
            userId: string;
            accessLevel: 'view' | 'contribute' | 'manage';
        }) => chatApi.shareSession(sessionId!, userId, accessLevel),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['chat-collaborators', sessionId] });
            setSelectedUserId(null);
            setSearchQuery('');
            toast({
                title: 'Zugriff gewährt',
                description: 'Der Benutzer hat jetzt Zugriff auf diesen Chat.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler',
                description: error.message || 'Zugriff konnte nicht gewährt werden.',
                variant: 'destructive',
            });
        },
    });

    const revokeMutation = useMutation({
        mutationFn: (userId: string) => chatApi.revokeAccess(sessionId!, userId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['chat-collaborators', sessionId] });
            toast({
                title: 'Zugriff entzogen',
                description: 'Der Benutzer hat keinen Zugriff mehr.',
            });
        },
        onError: (error: Error) => {
            toast({
                title: 'Fehler',
                description: error.message || 'Zugriff konnte nicht entzogen werden.',
                variant: 'destructive',
            });
        },
    });

    // Filter users - exclude already shared users
    const collaboratorUserIds = new Set(collaborators.map((c) => c.user_id));
    const availableUsers = users.filter(
        (user) =>
            !collaboratorUserIds.has(user.id) &&
            (searchQuery === '' ||
                user.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                user.email.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    // Handlers
    const handleShare = () => {
        if (!selectedUserId || !sessionId) return;
        shareMutation.mutate({
            userId: selectedUserId,
            accessLevel: selectedAccessLevel,
        });
    };

    const handleRevoke = (userId: string) => {
        if (!sessionId) return;
        revokeMutation.mutate(userId);
    };

    if (!sessionId) return null;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Share2 className="h-5 w-5" />
                        Chat teilen
                    </DialogTitle>
                    <DialogDescription>
                        {sessionTitle
                            ? `"${sessionTitle}" mit anderen Benutzern teilen.`
                            : 'Diesen Chat mit anderen Benutzern teilen.'}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* User Search & Add */}
                    <div className="space-y-3">
                        <Label>Benutzer hinzufügen</Label>

                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="Name oder E-Mail suchen..."
                                    value={searchQuery}
                                    onChange={(e) => {
                                        setSearchQuery(e.target.value);
                                        setSelectedUserId(null);
                                    }}
                                    className="pl-8"
                                />
                            </div>

                            <Select
                                value={selectedAccessLevel}
                                onValueChange={(v) =>
                                    setSelectedAccessLevel(v as 'view' | 'contribute' | 'manage')
                                }
                            >
                                <SelectTrigger className="w-[140px]">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="view">
                                        <div className="flex items-center gap-2">
                                            <Eye className="h-4 w-4" />
                                            Ansehen
                                        </div>
                                    </SelectItem>
                                    <SelectItem value="contribute">
                                        <div className="flex items-center gap-2">
                                            <Edit className="h-4 w-4" />
                                            Mitarbeiten
                                        </div>
                                    </SelectItem>
                                    <SelectItem value="manage">
                                        <div className="flex items-center gap-2">
                                            <Settings className="h-4 w-4" />
                                            Verwalten
                                        </div>
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        {/* User Search Results */}
                        {searchQuery && (
                            <ScrollArea className="h-[120px] rounded-md border">
                                {loadingUsers ? (
                                    <div className="flex items-center justify-center h-full">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    </div>
                                ) : availableUsers.length === 0 ? (
                                    <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                                        Keine Benutzer gefunden
                                    </div>
                                ) : (
                                    <div className="p-2 space-y-1">
                                        {availableUsers.slice(0, 5).map((user) => (
                                            <button
                                                key={user.id}
                                                onClick={() => setSelectedUserId(user.id)}
                                                className={cn(
                                                    'w-full flex items-center justify-between p-2 rounded-md hover:bg-accent transition-colors text-left',
                                                    selectedUserId === user.id && 'bg-accent'
                                                )}
                                            >
                                                <div>
                                                    <div className="font-medium">{user.name}</div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {user.email}
                                                    </div>
                                                </div>
                                                {selectedUserId === user.id && (
                                                    <Badge variant="secondary">Ausgewählt</Badge>
                                                )}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </ScrollArea>
                        )}

                        {/* Add Button */}
                        {selectedUserId && (
                            <Button
                                onClick={handleShare}
                                disabled={shareMutation.isPending}
                                className="w-full"
                            >
                                {shareMutation.isPending ? (
                                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                ) : (
                                    <UserPlus className="h-4 w-4 mr-2" />
                                )}
                                Benutzer hinzufügen
                            </Button>
                        )}
                    </div>

                    {/* Collaborators List */}
                    <div className="space-y-3">
                        <Label className="flex items-center gap-2">
                            <Users className="h-4 w-4" />
                            Zugriff ({collaborators.length})
                        </Label>

                        <ScrollArea className="h-[200px] rounded-md border">
                            {loadingCollaborators ? (
                                <div className="flex items-center justify-center h-full">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                </div>
                            ) : collaborators.length === 0 ? (
                                <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                                    Nur du hast Zugriff
                                </div>
                            ) : (
                                <div className="p-2 space-y-2">
                                    {collaborators.map((collab) => (
                                        <div
                                            key={collab.user_id}
                                            className="flex items-center justify-between p-2 rounded-md bg-muted/50"
                                        >
                                            <div className="flex items-center gap-3">
                                                <div className="flex items-center justify-center h-8 w-8 rounded-full bg-primary/10">
                                                    {getAccessLevelIcon(collab.access_level)}
                                                </div>
                                                <div>
                                                    <div className="font-medium">{collab.username}</div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {getAccessLevelLabel(collab.access_level)}
                                                        {!collab.is_owner &&
                                                            getAccessLevelDescription(collab.access_level) && (
                                                                <span className="ml-1">
                                                                    - {getAccessLevelDescription(collab.access_level)}
                                                                </span>
                                                            )}
                                                    </div>
                                                </div>
                                            </div>

                                            {!collab.is_owner && (
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => handleRevoke(collab.user_id)}
                                                    disabled={revokeMutation.isPending}
                                                >
                                                    {revokeMutation.isPending ? (
                                                        <Loader2 className="h-4 w-4 animate-spin" />
                                                    ) : (
                                                        <UserMinus className="h-4 w-4 text-destructive" />
                                                    )}
                                                </Button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </ScrollArea>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Schließen
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default ShareChatDialog;
