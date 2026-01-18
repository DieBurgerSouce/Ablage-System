/**
 * Slack Channel Configuration Dialog.
 *
 * Dialog fuer das Erstellen und Bearbeiten von Slack-Kanaelen.
 */

import { useState, useEffect } from 'react';
import { Hash, Loader2 } from 'lucide-react';
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
import { Checkbox } from '@/components/ui/checkbox';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import {
    useCreateSlackChannel,
    useUpdateSlackChannel,
    useSlackNotificationTypes,
} from '../hooks/use-slack-queries';
import type { SlackChannel, SlackChannelCreate, SlackChannelUpdate } from '../types';

interface SlackChannelDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    channel: SlackChannel | null;
}

export function SlackChannelDialog({ open, onOpenChange, channel }: SlackChannelDialogProps) {
    const isEditing = !!channel;

    const [channelId, setChannelId] = useState('');
    const [channelName, setChannelName] = useState('');
    const [channelType, setChannelType] = useState<'public' | 'private' | 'dm'>('public');
    const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
    const [minPriority, setMinPriority] = useState<'low' | 'normal' | 'high' | 'urgent'>('normal');
    const [isDefault, setIsDefault] = useState(false);
    const [includeContext, setIncludeContext] = useState(true);

    const { data: notificationTypes } = useSlackNotificationTypes();
    const createChannel = useCreateSlackChannel();
    const updateChannel = useUpdateSlackChannel();

    // Reset form when dialog opens/closes or channel changes
    useEffect(() => {
        if (open && channel) {
            setChannelId(channel.channel_id);
            setChannelName(channel.channel_name);
            setChannelType(channel.channel_type);
            setSelectedTypes(channel.notification_types);
            setMinPriority(channel.min_priority);
            setIsDefault(channel.is_default);
            setIncludeContext(channel.include_context);
        } else if (open && !channel) {
            // Reset fuer neuen Kanal
            setChannelId('');
            setChannelName('');
            setChannelType('public');
            setSelectedTypes([]);
            setMinPriority('normal');
            setIsDefault(false);
            setIncludeContext(true);
        }
    }, [open, channel]);

    const handleToggleType = (type: string) => {
        setSelectedTypes((prev) =>
            prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
        );
    };

    const handleSubmit = async () => {
        if (isEditing && channel) {
            const data: SlackChannelUpdate = {
                channel_name: channelName,
                notification_types: selectedTypes,
                min_priority: minPriority,
                is_default: isDefault,
                include_context: includeContext,
            };
            await updateChannel.mutateAsync({ channelId: channel.id, data });
        } else {
            const data: SlackChannelCreate = {
                channel_id: channelId,
                channel_name: channelName,
                channel_type: channelType,
                notification_types: selectedTypes,
                min_priority: minPriority,
                is_default: isDefault,
                include_context: includeContext,
            };
            await createChannel.mutateAsync(data);
        }
        onOpenChange(false);
    };

    const isLoading = createChannel.isPending || updateChannel.isPending;
    const isValid = channelId.length >= 9 && channelName.length >= 1;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Hash className="h-5 w-5" />
                        {isEditing ? 'Kanal bearbeiten' : 'Neuen Kanal hinzufuegen'}
                    </DialogTitle>
                    <DialogDescription>
                        {isEditing
                            ? 'Aendern Sie die Konfiguration des Slack-Kanals.'
                            : 'Konfigurieren Sie einen Slack-Kanal fuer Benachrichtigungen.'}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Channel ID */}
                    <div className="space-y-2">
                        <Label htmlFor="channel-id">Slack Channel ID</Label>
                        <Input
                            id="channel-id"
                            placeholder="C01234567"
                            value={channelId}
                            onChange={(e) => setChannelId(e.target.value.toUpperCase())}
                            disabled={isEditing}
                            maxLength={11}
                        />
                        <p className="text-xs text-muted-foreground">
                            Die Channel ID finden Sie in Slack unter Kanal-Details.
                        </p>
                    </div>

                    {/* Channel Name */}
                    <div className="space-y-2">
                        <Label htmlFor="channel-name">Kanal-Name</Label>
                        <div className="relative">
                            <Hash className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                id="channel-name"
                                placeholder="allgemein"
                                value={channelName}
                                onChange={(e) => setChannelName(e.target.value)}
                                className="pl-9"
                            />
                        </div>
                    </div>

                    {/* Channel Type */}
                    {!isEditing && (
                        <div className="space-y-2">
                            <Label>Kanal-Typ</Label>
                            <Select
                                value={channelType}
                                onValueChange={(v) => setChannelType(v as typeof channelType)}
                            >
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="public">Oeffentlich</SelectItem>
                                    <SelectItem value="private">Privat</SelectItem>
                                    <SelectItem value="dm">Direktnachricht</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    {/* Min Priority */}
                    <div className="space-y-2">
                        <Label>Mindest-Prioritaet</Label>
                        <Select
                            value={minPriority}
                            onValueChange={(v) => setMinPriority(v as typeof minPriority)}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="low">Niedrig</SelectItem>
                                <SelectItem value="normal">Normal</SelectItem>
                                <SelectItem value="high">Hoch</SelectItem>
                                <SelectItem value="urgent">Dringend</SelectItem>
                            </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                            Nur Nachrichten ab dieser Prioritaet werden an diesen Kanal gesendet.
                        </p>
                    </div>

                    {/* Notification Types */}
                    <div className="space-y-2">
                        <Label>Benachrichtigungstypen</Label>
                        <div className="flex flex-wrap gap-2 p-3 border rounded-md bg-muted/30">
                            {notificationTypes?.map((type) => (
                                <Badge
                                    key={type.type}
                                    variant={selectedTypes.includes(type.type) ? 'default' : 'outline'}
                                    className="cursor-pointer"
                                    onClick={() => handleToggleType(type.type)}
                                >
                                    {type.name}
                                </Badge>
                            ))}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Klicken Sie auf die Typen, die an diesen Kanal gesendet werden sollen.
                        </p>
                    </div>

                    {/* Options */}
                    <div className="space-y-3">
                        <div className="flex items-center space-x-2">
                            <Checkbox
                                id="is-default"
                                checked={isDefault}
                                onCheckedChange={(checked) => setIsDefault(!!checked)}
                            />
                            <div>
                                <Label htmlFor="is-default" className="cursor-pointer">
                                    Standard-Kanal
                                </Label>
                                <p className="text-xs text-muted-foreground">
                                    Nachrichten ohne spezifischen Kanal werden hierhin gesendet.
                                </p>
                            </div>
                        </div>

                        <div className="flex items-center space-x-2">
                            <Checkbox
                                id="include-context"
                                checked={includeContext}
                                onCheckedChange={(checked) => setIncludeContext(!!checked)}
                            />
                            <div>
                                <Label htmlFor="include-context" className="cursor-pointer">
                                    Kontext einschliessen
                                </Label>
                                <p className="text-xs text-muted-foreground">
                                    Zusaetzliche Details wie Dokument-ID, Benutzer, etc.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isLoading}>
                        Abbrechen
                    </Button>
                    <Button onClick={handleSubmit} disabled={!isValid || isLoading}>
                        {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                        {isEditing ? 'Speichern' : 'Hinzufuegen'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
