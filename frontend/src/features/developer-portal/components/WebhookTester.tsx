/**
 * Webhook Tester
 *
 * Verwaltet und testet Webhooks im Developer Portal.
 */

import { useState } from 'react';
import { Webhook, Plus, Trash2, Play, RefreshCw, Check, X, Copy, Loader2, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import {
  useWebhooks,
  useWebhookDeliveries,
  useCreateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  useRotateWebhookSecret,
  WEBHOOK_EVENT_TYPES,
  type WebhookSubscription,
} from '../hooks/useDeveloperPortal';

function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString('de-DE');
}

function WebhookCard({ webhook }: { webhook: WebhookSubscription }) {
  const [showSecret, setShowSecret] = useState(false);
  const [selectedEventType, setSelectedEventType] = useState('document.created');
  const [showDeliveries, setShowDeliveries] = useState(false);

  const deleteMutation = useDeleteWebhook();
  const testMutation = useTestWebhook();
  const rotateMutation = useRotateWebhookSecret();
  const { data: deliveries, isLoading: deliveriesLoading } = useWebhookDeliveries(
    showDeliveries ? webhook.id : ''
  );

  const handleTest = async () => {
    try {
      const result = await testMutation.mutateAsync({
        webhookId: webhook.id,
        request: { event_type: selectedEventType },
      });
      if (result.success) {
        toast.success(`Test erfolgreich (${result.status_code})`);
      } else {
        toast.error(`Test fehlgeschlagen: ${result.error}`);
      }
    } catch {
      toast.error('Test konnte nicht gestartet werden');
    }
  };

  const handleDelete = async () => {
    if (!confirm('Webhook wirklich löschen?')) return;
    try {
      await deleteMutation.mutateAsync(webhook.id);
      toast.success('Webhook gelöscht');
    } catch {
      toast.error('Löschen fehlgeschlagen');
    }
  };

  const handleRotateSecret = async () => {
    if (!confirm('Secret wirklich rotieren? Das alte Secret ist danach ungültig.')) return;
    try {
      const result = await rotateMutation.mutateAsync(webhook.id);
      toast.success('Neues Secret: ' + result.secret);
    } catch {
      toast.error('Rotation fehlgeschlagen');
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Webhook className="h-4 w-4" />
              {webhook.name}
              <Badge variant={webhook.is_active ? 'default' : 'secondary'}>
                {webhook.is_active ? 'Aktiv' : 'Inaktiv'}
              </Badge>
            </CardTitle>
            <CardDescription className="mt-1">{webhook.url}</CardDescription>
          </div>
          <Button variant="ghost" size="sm" onClick={handleDelete}>
            <Trash2 className="h-4 w-4 text-red-500" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Event Types */}
        <div>
          <Label className="text-xs text-muted-foreground">Events</Label>
          <div className="flex flex-wrap gap-1 mt-1">
            {webhook.event_types.map((event) => (
              <Badge key={event} variant="outline" className="text-xs">
                {event}
              </Badge>
            ))}
          </div>
        </div>

        {/* Statistics */}
        <div className="flex gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Erfolge:</span>
            <span className="ml-1 font-medium text-green-600">{webhook.success_count}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Fehler:</span>
            <span className="ml-1 font-medium text-red-600">{webhook.failure_count}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Letzter Aufruf:</span>
            <span className="ml-1">{formatDate(webhook.last_triggered_at)}</span>
          </div>
        </div>

        {/* Test Section */}
        <div className="flex items-end gap-2 pt-2 border-t">
          <div className="flex-1">
            <Label className="text-xs">Event-Typ für Test</Label>
            <Select value={selectedEventType} onValueChange={setSelectedEventType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WEBHOOK_EVENT_TYPES.map((event) => (
                  <SelectItem key={event.value} value={event.value}>
                    {event.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={handleTest} disabled={testMutation.isPending}>
            {testMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4 mr-2" />
            )}
            Testen
          </Button>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleRotateSecret}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Secret rotieren
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowDeliveries(!showDeliveries)}
          >
            <Clock className="h-4 w-4 mr-2" />
            {showDeliveries ? 'Verlauf ausblenden' : 'Verlauf anzeigen'}
          </Button>
        </div>

        {/* Delivery History */}
        {showDeliveries && (
          <div className="pt-2 border-t">
            <Label className="text-xs text-muted-foreground">Zustellungs-Verlauf</Label>
            {deliveriesLoading ? (
              <Skeleton className="h-32 w-full mt-2" />
            ) : deliveries && deliveries.length > 0 ? (
              <div className="mt-2 max-h-48 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Event</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs">Zeit</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {deliveries.slice(0, 10).map((delivery) => (
                      <TableRow key={delivery.id}>
                        <TableCell className="text-xs">{delivery.event_type}</TableCell>
                        <TableCell>
                          <Badge
                            variant={delivery.status === 'success' ? 'default' : 'destructive'}
                            className="text-xs"
                          >
                            {delivery.status === 'success' ? (
                              <Check className="h-3 w-3 mr-1" />
                            ) : (
                              <X className="h-3 w-3 mr-1" />
                            )}
                            {delivery.status_code || delivery.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">
                          {formatDate(delivery.delivered_at || delivery.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground mt-2">
                Noch keine Zustellungen
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CreateWebhookDialog() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  const createMutation = useCreateWebhook();

  const handleCreate = async () => {
    if (!name || !url || selectedEvents.length === 0) {
      toast.error('Bitte alle Pflichtfelder ausfüllen');
      return;
    }

    try {
      const result = await createMutation.mutateAsync({
        name,
        url,
        description,
        event_types: selectedEvents,
      });
      setNewSecret(result.secret);
      toast.success('Webhook erstellt');
    } catch {
      toast.error('Erstellung fehlgeschlagen');
    }
  };

  const handleClose = () => {
    setOpen(false);
    setName('');
    setUrl('');
    setDescription('');
    setSelectedEvents([]);
    setNewSecret(null);
  };

  const handleEventToggle = (event: string) => {
    setSelectedEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Webhook erstellen
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Neuen Webhook erstellen</DialogTitle>
          <DialogDescription>
            Konfigurieren Sie einen Webhook für Event-Benachrichtigungen
          </DialogDescription>
        </DialogHeader>

        {newSecret ? (
          <div className="space-y-4">
            <div className="p-4 bg-green-50 dark:bg-green-950 rounded-lg border border-green-200 dark:border-green-800">
              <p className="text-sm font-medium text-green-800 dark:text-green-200 mb-2">
                Webhook erfolgreich erstellt!
              </p>
              <p className="text-xs text-green-600 dark:text-green-400 mb-3">
                Speichern Sie das Secret jetzt - es wird nicht erneut angezeigt.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 p-2 bg-white dark:bg-gray-900 rounded text-xs font-mono break-all">
                  {newSecret}
                </code>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    navigator.clipboard.writeText(newSecret);
                    toast.success('Secret kopiert');
                  }}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={handleClose}>Schließen</Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                placeholder="Mein Webhook"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="url">URL *</Label>
              <Input
                id="url"
                type="url"
                placeholder="https://example.com/webhook"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="description">Beschreibung</Label>
              <Input
                id="description"
                placeholder="Optional"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            <div className="grid gap-2">
              <Label>Events *</Label>
              <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto p-2 border rounded-lg">
                {WEBHOOK_EVENT_TYPES.map((event) => (
                  <div key={event.value} className="flex items-center space-x-2">
                    <Checkbox
                      id={event.value}
                      checked={selectedEvents.includes(event.value)}
                      onCheckedChange={() => handleEventToggle(event.value)}
                    />
                    <label
                      htmlFor={event.value}
                      className="text-xs cursor-pointer"
                    >
                      {event.label}
                    </label>
                  </div>
                ))}
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={handleClose}>
                Abbrechen
              </Button>
              <Button onClick={handleCreate} disabled={createMutation.isPending}>
                {createMutation.isPending && (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                )}
                Erstellen
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function WebhookTester() {
  const { data: webhooks, isLoading } = useWebhooks();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-10 w-40" />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Webhooks</h3>
          <p className="text-sm text-muted-foreground">
            Verwalten und testen Sie Ihre Webhook-Abonnements
          </p>
        </div>
        <CreateWebhookDialog />
      </div>

      {webhooks && webhooks.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {webhooks.map((webhook) => (
            <WebhookCard key={webhook.id} webhook={webhook} />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="py-12 text-center">
            <Webhook className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p className="text-muted-foreground">Keine Webhooks konfiguriert</p>
            <p className="text-sm text-muted-foreground mt-1">
              Erstellen Sie einen Webhook für Echtzeit-Benachrichtigungen
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
