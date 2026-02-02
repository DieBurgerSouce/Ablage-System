/**
 * NotificationPreferencesPage
 *
 * Hauptseite fuer Benachrichtigungs-Einstellungen.
 * Ermoeglicht Konfiguration von Kanaelen, Schweregrad-Matrix und Ruhezeiten.
 */

import { useState } from 'react';
import {
  Bell,
  Settings2,
  Moon,
  ArrowRight,
  Shield,
  RefreshCw,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

import { ChannelToggle } from './components/ChannelToggle';
import { SeverityMatrix } from './components/SeverityMatrix';
import { QuietHoursForm } from './components/QuietHoursForm';
import { TestNotificationButton } from './components/TestNotificationButton';
import { EscalationChainView } from './components/EscalationChainView';
import { GdprConsentBanner } from './components/GdprConsentBanner';

import {
  useNotificationPreferences,
  useChannelStatus,
  useEscalationChain,
  useToggleChannel,
  useTestNotification,
  useUpdateNotificationPreferences,
} from './hooks';
import type { NotificationChannel, ChannelConfig } from './types';

export function NotificationPreferencesPage() {
  const [activeTab, setActiveTab] = useState('channels');
  const [showGdprBanner, setShowGdprBanner] = useState(false);
  const [pendingGdprChannel, setPendingGdprChannel] = useState<NotificationChannel | null>(null);

  // Queries
  const { data: preferences, isLoading: prefsLoading } = useNotificationPreferences();
  const { data: channelStatus, isLoading: channelsLoading } = useChannelStatus();
  const { data: escalationChain, isLoading: escalationLoading } = useEscalationChain();

  // Mutations
  const toggleChannel = useToggleChannel();
  const testNotification = useTestNotification();
  const updatePreferences = useUpdateNotificationPreferences();

  const isLoading = prefsLoading || channelsLoading || escalationLoading;

  // Handler fuer Kanal-Toggle mit GDPR-Check
  const handleChannelToggle = (channel: NotificationChannel, enabled: boolean) => {
    const channelConfig = channelStatus?.find((c: ChannelConfig) => c.channel === channel);

    if (enabled && channelConfig?.gdprRequired) {
      // GDPR-Einwilligung erforderlich
      setPendingGdprChannel(channel);
      setShowGdprBanner(true);
      return;
    }

    toggleChannel.mutate({ channel, enabled });
  };

  // Handler fuer GDPR-Einwilligung
  const handleGdprConsent = (consented: boolean) => {
    if (consented && pendingGdprChannel) {
      toggleChannel.mutate({ channel: pendingGdprChannel, enabled: true });
    }
    setShowGdprBanner(false);
    setPendingGdprChannel(null);
  };

  // Handler fuer Test-Benachrichtigung
  const handleTestNotification = (channel: NotificationChannel) => {
    testNotification.mutate({ channel });
  };

  // Handler fuer globales Aktivieren/Deaktivieren
  const handleGlobalToggle = (enabled: boolean) => {
    updatePreferences.mutate({ enabled });
  };

  if (isLoading) {
    return (
      <div className="container mx-auto py-6 space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
              <Bell className="h-8 w-8" />
              Benachrichtigungen
            </h1>
            <p className="text-muted-foreground mt-1">
              Konfigurieren Sie, wie und wann Sie benachrichtigt werden moechten.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <Label htmlFor="global-toggle" className="text-sm">
              Alle Benachrichtigungen
            </Label>
            <Switch
              id="global-toggle"
              checked={preferences?.enabled ?? true}
              onCheckedChange={handleGlobalToggle}
              disabled={updatePreferences.isPending}
            />
          </div>
        </div>

        {/* GDPR Banner */}
        {showGdprBanner && (
          <GdprConsentBanner
            channel={pendingGdprChannel!}
            onConsent={handleGdprConsent}
            onDismiss={() => {
              setShowGdprBanner(false);
              setPendingGdprChannel(null);
            }}
          />
        )}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="channels" className="flex items-center gap-2">
              <Settings2 className="h-4 w-4" />
              Kanaele
            </TabsTrigger>
            <TabsTrigger value="severity" className="flex items-center gap-2">
              <Shield className="h-4 w-4" />
              Schweregrad
            </TabsTrigger>
            <TabsTrigger value="quiet-hours" className="flex items-center gap-2">
              <Moon className="h-4 w-4" />
              Ruhezeiten
            </TabsTrigger>
            <TabsTrigger value="escalation" className="flex items-center gap-2">
              <ArrowRight className="h-4 w-4" />
              Eskalation
            </TabsTrigger>
          </TabsList>

          {/* Kanaele Tab */}
          <TabsContent value="channels" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Benachrichtigungskanaele</CardTitle>
                <CardDescription>
                  Aktivieren oder deaktivieren Sie einzelne Kanaele. DSGVO-relevante
                  Kanaele (SMS, WhatsApp) erfordern Ihre explizite Einwilligung.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                {channelStatus?.map((channel: ChannelConfig) => (
                  <ChannelToggle
                    key={channel.channel}
                    channel={channel}
                    onToggle={handleChannelToggle}
                    onTest={handleTestNotification}
                    isLoading={toggleChannel.isPending || testNotification.isPending}
                    disabled={!preferences?.enabled}
                  />
                ))}
              </CardContent>
            </Card>

            {/* Test-Sektion */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <RefreshCw className="h-5 w-5" />
                  Test-Benachrichtigung
                </CardTitle>
                <CardDescription>
                  Senden Sie eine Test-Nachricht an einen Kanal, um die Konfiguration zu pruefen.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {channelStatus
                    ?.filter((c: ChannelConfig) => c.enabled && c.configured)
                    .map((channel: ChannelConfig) => (
                      <TestNotificationButton
                        key={channel.channel}
                        channel={channel.channel}
                        onTest={handleTestNotification}
                        isLoading={testNotification.isPending}
                      />
                    ))}
                  {channelStatus?.filter((c: ChannelConfig) => c.enabled && c.configured).length === 0 && (
                    <Alert>
                      <AlertTitle>Keine aktiven Kanaele</AlertTitle>
                      <AlertDescription>
                        Aktivieren Sie mindestens einen Kanal, um Test-Benachrichtigungen zu senden.
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Schweregrad Tab */}
          <TabsContent value="severity">
            <Card>
              <CardHeader>
                <CardTitle>Schweregrad-Matrix</CardTitle>
                <CardDescription>
                  Legen Sie fest, welche Kanaele bei welchem Schweregrad verwendet werden sollen.
                  Kritische Meldungen werden immer ueber alle aktivierten Kanaele gesendet.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <SeverityMatrix
                  preferences={preferences}
                  channelStatus={channelStatus ?? []}
                  disabled={!preferences?.enabled}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Ruhezeiten Tab */}
          <TabsContent value="quiet-hours">
            <Card>
              <CardHeader>
                <CardTitle>Ruhezeiten</CardTitle>
                <CardDescription>
                  Konfigurieren Sie Zeitraeume, in denen keine Benachrichtigungen gesendet werden.
                  Kritische Alerts koennen optional trotzdem zugestellt werden.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <QuietHoursForm
                  preferences={preferences}
                  disabled={!preferences?.enabled}
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Eskalation Tab */}
          <TabsContent value="escalation">
            <Card>
              <CardHeader>
                <CardTitle>Eskalationskette</CardTitle>
                <CardDescription>
                  Wenn eine kritische Benachrichtigung nicht bestaetigt wird, eskaliert das
                  System automatisch zu weiteren Kanaelen. Die Zeiten sind konfigurierbar.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <EscalationChainView
                  escalationChain={escalationChain ?? []}
                  preferences={preferences}
                  disabled={!preferences?.enabled}
                />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
    </div>
  );
}

export default NotificationPreferencesPage;
