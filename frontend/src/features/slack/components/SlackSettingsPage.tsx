/**
 * Slack Integration Settings Page.
 *
 * Admin-Seite fuer die Slack-Integration:
 * - Verbindungs-Status
 * - Kanal-Konfiguration
 * - Nachrichten-Verlauf
 * - User-Mappings
 */

import { useState } from 'react';
import {
    MessageSquare,
    Hash,
    Users,
    Activity,
    Send,
    Settings,
    CheckCircle,
    XCircle,
    AlertTriangle,
    RefreshCw,
    Plus,
    Trash2,
    MoreHorizontal,
    ExternalLink,
} from 'lucide-react';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
    useSlackStatus,
    useSlackStatistics,
    useSlackChannels,
    useSlackMessages,
    useDeleteSlackChannel,
    useSendTestMessage,
} from '../hooks/use-slack-queries';
import { SlackChannelDialog } from './SlackChannelDialog';
import { SlackTestDialog } from './SlackTestDialog';
import type { SlackChannel, SlackMessageLog } from '../types';

export function SlackSettingsPage() {
    const [activeTab, setActiveTab] = useState('overview');
    const [channelDialogOpen, setChannelDialogOpen] = useState(false);
    const [testDialogOpen, setTestDialogOpen] = useState(false);
    const [editingChannel, setEditingChannel] = useState<SlackChannel | null>(null);
    const [deleteChannelId, setDeleteChannelId] = useState<string | null>(null);

    const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useSlackStatus();
    const { data: statistics, isLoading: statsLoading } = useSlackStatistics();
    const { data: channelsData, isLoading: channelsLoading } = useSlackChannels();
    const { data: messagesData, isLoading: messagesLoading } = useSlackMessages({ limit: 20 });

    const deleteChannel = useDeleteSlackChannel();

    const handleEditChannel = (channel: SlackChannel) => {
        setEditingChannel(channel);
        setChannelDialogOpen(true);
    };

    const handleDeleteChannel = () => {
        if (deleteChannelId) {
            deleteChannel.mutate(deleteChannelId);
            setDeleteChannelId(null);
        }
    };

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleString('de-DE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    const getStatusBadge = (msgStatus: string) => {
        switch (msgStatus) {
            case 'sent':
                return <Badge variant="default" className="bg-green-600">Gesendet</Badge>;
            case 'failed':
                return <Badge variant="destructive">Fehlgeschlagen</Badge>;
            case 'rate_limited':
                return <Badge variant="secondary">Rate Limit</Badge>;
            default:
                return <Badge variant="outline">Ausstehend</Badge>;
        }
    };

    return (
        <div className="container mx-auto py-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <MessageSquare className="h-6 w-6" />
                        Slack-Integration
                    </h1>
                    <p className="text-muted-foreground">
                        Verwalten Sie Slack-Benachrichtigungen fuer Ihr Team.
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={() => setTestDialogOpen(true)}>
                        <Send className="h-4 w-4 mr-2" />
                        Test senden
                    </Button>
                    <Button onClick={() => {
                        setEditingChannel(null);
                        setChannelDialogOpen(true);
                    }}>
                        <Plus className="h-4 w-4 mr-2" />
                        Kanal hinzufuegen
                    </Button>
                </div>
            </div>

            {/* Status Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {/* Connection Status */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Activity className="h-4 w-4" />
                            Verbindungs-Status
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {statusLoading ? (
                            <Skeleton className="h-8 w-24" />
                        ) : status?.enabled ? (
                            <div className="flex items-center gap-2">
                                <CheckCircle className="h-5 w-5 text-green-600" />
                                <span className="font-semibold text-green-600">Aktiv</span>
                            </div>
                        ) : (
                            <div className="flex items-center gap-2">
                                <XCircle className="h-5 w-5 text-muted-foreground" />
                                <span className="font-semibold text-muted-foreground">Inaktiv</span>
                            </div>
                        )}
                        <Button
                            variant="ghost"
                            size="sm"
                            className="mt-2 h-7 px-2 text-xs"
                            onClick={() => refetchStatus()}
                        >
                            <RefreshCw className="h-3 w-3 mr-1" />
                            Aktualisieren
                        </Button>
                    </CardContent>
                </Card>

                {/* Channels */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Hash className="h-4 w-4" />
                            Kanaele
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {statsLoading ? (
                            <Skeleton className="h-8 w-16" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">
                                    {statistics?.active_channels ?? 0}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    von {statistics?.total_channels ?? 0} konfiguriert
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>

                {/* Messages 24h */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <MessageSquare className="h-4 w-4" />
                            Nachrichten (24h)
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {statsLoading ? (
                            <Skeleton className="h-8 w-16" />
                        ) : (
                            <>
                                <div className="text-2xl font-bold">
                                    {statistics?.messages_last_24h ?? 0}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    {statistics?.messages_last_7d ?? 0} in 7 Tagen
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>

                {/* Failed Messages */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4" />
                            Fehlgeschlagen
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {statsLoading ? (
                            <Skeleton className="h-8 w-16" />
                        ) : (
                            <>
                                <div className={cn(
                                    "text-2xl font-bold",
                                    (statistics?.failed_messages ?? 0) > 0 && "text-red-600"
                                )}>
                                    {statistics?.failed_messages ?? 0}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    Gesamt
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList>
                    <TabsTrigger value="overview" className="gap-2">
                        <Settings className="h-4 w-4" />
                        Uebersicht
                    </TabsTrigger>
                    <TabsTrigger value="channels" className="gap-2">
                        <Hash className="h-4 w-4" />
                        Kanaele
                    </TabsTrigger>
                    <TabsTrigger value="messages" className="gap-2">
                        <MessageSquare className="h-4 w-4" />
                        Nachrichten
                    </TabsTrigger>
                    <TabsTrigger value="users" className="gap-2">
                        <Users className="h-4 w-4" />
                        Benutzer
                    </TabsTrigger>
                </TabsList>

                {/* Overview Tab */}
                <TabsContent value="overview" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>Konfiguration</CardTitle>
                            <CardDescription>
                                Status der Slack-Integration und Verbindungsdetails.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {statusLoading ? (
                                <div className="space-y-2">
                                    <Skeleton className="h-4 w-full" />
                                    <Skeleton className="h-4 w-3/4" />
                                </div>
                            ) : (
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <p className="text-sm font-medium">Webhook</p>
                                        <p className="text-sm text-muted-foreground">
                                            {status?.webhook_configured ? (
                                                <span className="text-green-600">Konfiguriert</span>
                                            ) : (
                                                <span className="text-muted-foreground">Nicht konfiguriert</span>
                                            )}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium">Bot-Token</p>
                                        <p className="text-sm text-muted-foreground">
                                            {status?.bot_token_configured ? (
                                                <span className="text-green-600">Konfiguriert</span>
                                            ) : (
                                                <span className="text-muted-foreground">Nicht konfiguriert</span>
                                            )}
                                        </p>
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium">Standard-Kanal</p>
                                        <p className="text-sm text-muted-foreground">
                                            #{status?.default_channel || '-'}
                                        </p>
                                    </div>
                                    {status?.bot_test?.team && (
                                        <div>
                                            <p className="text-sm font-medium">Workspace</p>
                                            <p className="text-sm text-muted-foreground">
                                                {status.bot_test.team}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Einrichtung</CardTitle>
                            <CardDescription>
                                Anleitung zur Konfiguration der Slack-Integration.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="space-y-2">
                                <h4 className="font-medium">1. Slack App erstellen</h4>
                                <p className="text-sm text-muted-foreground">
                                    Erstellen Sie eine Slack App unter{' '}
                                    <a
                                        href="https://api.slack.com/apps"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-primary hover:underline inline-flex items-center gap-1"
                                    >
                                        api.slack.com/apps
                                        <ExternalLink className="h-3 w-3" />
                                    </a>
                                </p>
                            </div>
                            <div className="space-y-2">
                                <h4 className="font-medium">2. Incoming Webhook aktivieren</h4>
                                <p className="text-sm text-muted-foreground">
                                    Aktivieren Sie "Incoming Webhooks" und kopieren Sie die Webhook-URL
                                    in die Umgebungsvariable <code className="bg-muted px-1 rounded">SLACK_WEBHOOK_URL</code>.
                                </p>
                            </div>
                            <div className="space-y-2">
                                <h4 className="font-medium">3. Bot-Token (optional)</h4>
                                <p className="text-sm text-muted-foreground">
                                    Fuer erweiterte Funktionen erstellen Sie unter "OAuth & Permissions"
                                    einen Bot mit den Scopes: <code className="bg-muted px-1 rounded">chat:write</code>,{' '}
                                    <code className="bg-muted px-1 rounded">users:read</code>.
                                </p>
                            </div>
                            <div className="space-y-2">
                                <h4 className="font-medium">4. Integration aktivieren</h4>
                                <p className="text-sm text-muted-foreground">
                                    Setzen Sie <code className="bg-muted px-1 rounded">SLACK_ENABLED=true</code> in Ihrer Konfiguration.
                                </p>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Channels Tab */}
                <TabsContent value="channels">
                    <Card>
                        <CardHeader>
                            <CardTitle>Konfigurierte Kanaele</CardTitle>
                            <CardDescription>
                                Slack-Kanaele fuer verschiedene Benachrichtigungstypen.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {channelsLoading ? (
                                <div className="space-y-2">
                                    <Skeleton className="h-12 w-full" />
                                    <Skeleton className="h-12 w-full" />
                                </div>
                            ) : channelsData?.items.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <Hash className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                    <p>Noch keine Kanaele konfiguriert.</p>
                                    <Button
                                        variant="outline"
                                        className="mt-4"
                                        onClick={() => {
                                            setEditingChannel(null);
                                            setChannelDialogOpen(true);
                                        }}
                                    >
                                        <Plus className="h-4 w-4 mr-2" />
                                        Ersten Kanal hinzufuegen
                                    </Button>
                                </div>
                            ) : (
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Kanal</TableHead>
                                            <TableHead>Typen</TableHead>
                                            <TableHead>Prioritaet</TableHead>
                                            <TableHead>Status</TableHead>
                                            <TableHead>Nachrichten</TableHead>
                                            <TableHead className="text-right">Aktionen</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {channelsData?.items.map((channel) => (
                                            <TableRow key={channel.id}>
                                                <TableCell>
                                                    <div className="flex items-center gap-2">
                                                        <Hash className="h-4 w-4 text-muted-foreground" />
                                                        <span className="font-medium">{channel.channel_name}</span>
                                                        {channel.is_default && (
                                                            <Badge variant="secondary" className="text-xs">Standard</Badge>
                                                        )}
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex flex-wrap gap-1">
                                                        {channel.notification_types.slice(0, 2).map((type) => (
                                                            <Badge key={type} variant="outline" className="text-xs">
                                                                {type}
                                                            </Badge>
                                                        ))}
                                                        {channel.notification_types.length > 2 && (
                                                            <Badge variant="outline" className="text-xs">
                                                                +{channel.notification_types.length - 2}
                                                            </Badge>
                                                        )}
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant="outline">{channel.min_priority}</Badge>
                                                </TableCell>
                                                <TableCell>
                                                    {channel.is_active ? (
                                                        <Badge variant="default" className="bg-green-600">Aktiv</Badge>
                                                    ) : (
                                                        <Badge variant="secondary">Inaktiv</Badge>
                                                    )}
                                                </TableCell>
                                                <TableCell>{channel.message_count}</TableCell>
                                                <TableCell className="text-right">
                                                    <DropdownMenu>
                                                        <DropdownMenuTrigger asChild>
                                                            <Button variant="ghost" size="sm">
                                                                <MoreHorizontal className="h-4 w-4" />
                                                            </Button>
                                                        </DropdownMenuTrigger>
                                                        <DropdownMenuContent align="end">
                                                            <DropdownMenuItem onClick={() => handleEditChannel(channel)}>
                                                                Bearbeiten
                                                            </DropdownMenuItem>
                                                            <DropdownMenuItem
                                                                className="text-destructive"
                                                                onClick={() => setDeleteChannelId(channel.id)}
                                                            >
                                                                Loeschen
                                                            </DropdownMenuItem>
                                                        </DropdownMenuContent>
                                                    </DropdownMenu>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Messages Tab */}
                <TabsContent value="messages">
                    <Card>
                        <CardHeader>
                            <CardTitle>Nachrichten-Verlauf</CardTitle>
                            <CardDescription>
                                Die letzten gesendeten Slack-Nachrichten.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {messagesLoading ? (
                                <div className="space-y-2">
                                    <Skeleton className="h-12 w-full" />
                                    <Skeleton className="h-12 w-full" />
                                </div>
                            ) : messagesData?.items.length === 0 ? (
                                <div className="text-center py-8 text-muted-foreground">
                                    <MessageSquare className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                    <p>Noch keine Nachrichten gesendet.</p>
                                </div>
                            ) : (
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Zeitpunkt</TableHead>
                                            <TableHead>Kanal</TableHead>
                                            <TableHead>Typ</TableHead>
                                            <TableHead>Titel</TableHead>
                                            <TableHead>Status</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {messagesData?.items.map((message) => (
                                            <TableRow key={message.id}>
                                                <TableCell className="text-sm">
                                                    {formatDate(message.created_at)}
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex items-center gap-1">
                                                        <Hash className="h-3 w-3 text-muted-foreground" />
                                                        <span className="text-sm">{message.slack_channel_id}</span>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant="outline" className="text-xs">
                                                        {message.notification_type}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell className="max-w-[200px] truncate">
                                                    {message.title}
                                                </TableCell>
                                                <TableCell>
                                                    {getStatusBadge(message.status)}
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Users Tab */}
                <TabsContent value="users">
                    <Card>
                        <CardHeader>
                            <CardTitle>Benutzer-Verknuepfungen</CardTitle>
                            <CardDescription>
                                Verknuepfte Slack-Benutzer fuer Direktnachrichten und Erwaehnungen.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="text-center py-8 text-muted-foreground">
                                <Users className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                <p>Benutzer koennen ihre Slack-Verknuepfung in den Einstellungen vornehmen.</p>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* Dialogs */}
            <SlackChannelDialog
                open={channelDialogOpen}
                onOpenChange={setChannelDialogOpen}
                channel={editingChannel}
            />

            <SlackTestDialog
                open={testDialogOpen}
                onOpenChange={setTestDialogOpen}
            />

            {/* Delete Confirmation */}
            <AlertDialog open={!!deleteChannelId} onOpenChange={() => setDeleteChannelId(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Kanal loeschen?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Der Slack-Kanal wird aus der Konfiguration entfernt.
                            Bestehende Nachrichten-Logs bleiben erhalten.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                        <AlertDialogAction onClick={handleDeleteChannel}>
                            <Trash2 className="h-4 w-4 mr-2" />
                            Loeschen
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}
