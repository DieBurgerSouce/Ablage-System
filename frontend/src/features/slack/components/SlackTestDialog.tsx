/**
 * Slack Test Message Dialog.
 *
 * Dialog zum Senden einer Test-Nachricht an Slack.
 */

import { useState } from 'react';
import { Send, Loader2, CheckCircle, XCircle } from 'lucide-react';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useSendTestMessage, useSlackNotificationTypes } from '../hooks/use-slack-queries';

interface SlackTestDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

export function SlackTestDialog({ open, onOpenChange }: SlackTestDialogProps) {
    const [message, setMessage] = useState('Dies ist eine Test-Nachricht vom Ablage-System.');
    const [notificationType, setNotificationType] = useState('system_alert');
    const [priority, setPriority] = useState<'low' | 'normal' | 'high' | 'urgent'>('normal');
    const [result, setResult] = useState<{ success: boolean; error?: string } | null>(null);

    const { data: notificationTypes } = useSlackNotificationTypes();
    const sendTest = useSendTestMessage();

    const handleSend = async () => {
        setResult(null);
        const response = await sendTest.mutateAsync({
            message,
            notification_type: notificationType,
            priority,
        });
        setResult({ success: response.success, error: response.error ?? undefined });
    };

    const handleClose = () => {
        setResult(null);
        onOpenChange(false);
    };

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Send className="h-5 w-5" />
                        Test-Nachricht senden
                    </DialogTitle>
                    <DialogDescription>
                        Senden Sie eine Test-Nachricht, um die Slack-Integration zu prüfen.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Result Alert */}
                    {result && (
                        <Alert variant={result.success ? 'default' : 'destructive'}>
                            {result.success ? (
                                <CheckCircle className="h-4 w-4" />
                            ) : (
                                <XCircle className="h-4 w-4" />
                            )}
                            <AlertTitle>
                                {result.success ? 'Erfolgreich' : 'Fehlgeschlagen'}
                            </AlertTitle>
                            <AlertDescription>
                                {result.success
                                    ? 'Die Test-Nachricht wurde an Slack gesendet.'
                                    : result.error || 'Die Nachricht konnte nicht gesendet werden.'}
                            </AlertDescription>
                        </Alert>
                    )}

                    {/* Message */}
                    <div className="space-y-2">
                        <Label htmlFor="test-message">Nachricht</Label>
                        <Textarea
                            id="test-message"
                            placeholder="Ihre Test-Nachricht..."
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            rows={3}
                        />
                    </div>

                    {/* Notification Type */}
                    <div className="space-y-2">
                        <Label>Benachrichtigungstyp</Label>
                        <Select value={notificationType} onValueChange={setNotificationType}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {notificationTypes?.map((type) => (
                                    <SelectItem key={type.type} value={type.type}>
                                        {type.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Priority */}
                    <div className="space-y-2">
                        <Label>Priorität</Label>
                        <Select
                            value={priority}
                            onValueChange={(v) => setPriority(v as typeof priority)}
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
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={handleClose}>
                        Schließen
                    </Button>
                    <Button onClick={handleSend} disabled={sendTest.isPending || !message}>
                        {sendTest.isPending ? (
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                            <Send className="h-4 w-4 mr-2" />
                        )}
                        Senden
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
