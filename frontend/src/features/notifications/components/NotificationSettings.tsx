/**
 * Notification Center - Settings Component
 *
 * Einstellungen für Benachrichtigungen
 */

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { AlertCircle, Loader2 } from 'lucide-react';
import {
  useNotificationSettings,
  useUpdateSettings
} from '../hooks/useNotifications';
import { NotificationPriority, NotificationType } from '../types';
import type { NotificationSettingsUpdate } from '../types';

export function NotificationSettings() {
  const { data: settings, isLoading, isError } = useNotificationSettings();
  const updateSettingsMutation = useUpdateSettings();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !settings) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12 text-destructive gap-2">
          <AlertCircle className="h-8 w-8" />
          <p className="text-sm">Fehler beim Laden der Einstellungen</p>
        </CardContent>
      </Card>
    );
  }

  const handleUpdate = (update: NotificationSettingsUpdate) => {
    updateSettingsMutation.mutate(update);
  };

  const togglePriority = (priority: NotificationPriority) => {
    const newPriorities = settings.priorities.includes(priority)
      ? settings.priorities.filter((p) => p !== priority)
      : [...settings.priorities, priority];

    handleUpdate({ priorities: newPriorities });
  };

  const toggleType = (type: NotificationType) => {
    const newTypes = settings.types.includes(type)
      ? settings.types.filter((t) => t !== type)
      : [...settings.types, type];

    handleUpdate({ types: newTypes });
  };

  return (
    <div className="space-y-6">
      {/* Benachrichtigungskanäle */}
      <Card>
        <CardHeader>
          <CardTitle>Benachrichtigungskanäle</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="email-notifications">
                E-Mail-Benachrichtigungen
              </Label>
              <p className="text-sm text-muted-foreground">
                Erhalten Sie Benachrichtigungen per E-Mail
              </p>
            </div>
            <Switch
              id="email-notifications"
              checked={settings.email_enabled}
              onCheckedChange={(checked) =>
                handleUpdate({ email_enabled: checked })
              }
              disabled={updateSettingsMutation.isPending}
            />
          </div>

          <Separator />

          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="push-notifications">
                Push-Benachrichtigungen
              </Label>
              <p className="text-sm text-muted-foreground">
                Erhalten Sie Browser-Benachrichtigungen
              </p>
            </div>
            <Switch
              id="push-notifications"
              checked={settings.push_enabled}
              onCheckedChange={(checked) =>
                handleUpdate({ push_enabled: checked })
              }
              disabled={updateSettingsMutation.isPending}
            />
          </div>
        </CardContent>
      </Card>

      {/* Prioritäten */}
      <Card>
        <CardHeader>
          <CardTitle>Prioritäten</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center space-x-2">
            <Checkbox
              id="priority-critical"
              checked={settings.priorities.includes(
                NotificationPriority.CRITICAL
              )}
              onCheckedChange={() => togglePriority(NotificationPriority.CRITICAL)}
              disabled={updateSettingsMutation.isPending}
            />
            <Label
              htmlFor="priority-critical"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Kritische Benachrichtigungen
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="priority-warning"
              checked={settings.priorities.includes(
                NotificationPriority.WARNING
              )}
              onCheckedChange={() => togglePriority(NotificationPriority.WARNING)}
              disabled={updateSettingsMutation.isPending}
            />
            <Label
              htmlFor="priority-warning"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Warnungen
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="priority-info"
              checked={settings.priorities.includes(NotificationPriority.INFO)}
              onCheckedChange={() => togglePriority(NotificationPriority.INFO)}
              disabled={updateSettingsMutation.isPending}
            />
            <Label
              htmlFor="priority-info"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Informationen
            </Label>
          </div>
        </CardContent>
      </Card>

      {/* Benachrichtigungstypen */}
      <Card>
        <CardHeader>
          <CardTitle>Benachrichtigungstypen</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center space-x-2">
            <Checkbox
              id="type-system"
              checked={settings.types.includes(NotificationType.SYSTEM)}
              onCheckedChange={() => toggleType(NotificationType.SYSTEM)}
              disabled={updateSettingsMutation.isPending}
            />
            <Label
              htmlFor="type-system"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              System-Benachrichtigungen
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="type-document"
              checked={settings.types.includes(NotificationType.DOCUMENT)}
              onCheckedChange={() => toggleType(NotificationType.DOCUMENT)}
              disabled={updateSettingsMutation.isPending}
            />
            <Label
              htmlFor="type-document"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Dokument-Benachrichtigungen
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="type-invoice"
              checked={settings.types.includes(NotificationType.INVOICE)}
              onCheckedChange={() => toggleType(NotificationType.INVOICE)}
              disabled={updateSettingsMutation.isPending}
            />
            <Label
              htmlFor="type-invoice"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Rechnungs-Benachrichtigungen
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="type-workflow"
              checked={settings.types.includes(NotificationType.WORKFLOW)}
              onCheckedChange={() => toggleType(NotificationType.WORKFLOW)}
              disabled={updateSettingsMutation.isPending}
            />
            <Label
              htmlFor="type-workflow"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Workflow-Benachrichtigungen
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="type-alert"
              checked={settings.types.includes(NotificationType.ALERT)}
              onCheckedChange={() => toggleType(NotificationType.ALERT)}
              disabled={updateSettingsMutation.isPending}
            />
            <Label
              htmlFor="type-alert"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              Sicherheits-Benachrichtigungen
            </Label>
          </div>
        </CardContent>
      </Card>

      {/* Aktualisiert am */}
      <p className="text-xs text-muted-foreground text-center">
        Zuletzt aktualisiert:{' '}
        {new Date(settings.updated_at).toLocaleString('de-DE')}
      </p>
    </div>
  );
}
