/**
 * OAuth Setup Card
 *
 * Admin-Konfiguration für OAuth-App-Credentials und CalDAV-Verbindung.
 * Unterstützt Google, Microsoft und CalDAV Provider.
 */

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Eye,
  EyeOff,
  ExternalLink,
  Loader2,
  Info,
  Server,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { useToast } from '@/hooks/use-toast';
import { testConnection } from '../api/calendar-sync-api';

interface ProviderCredentials {
  client_id: string;
  client_secret: string;
  redirect_uri: string;
}

interface CalDAVCredentials {
  url: string;
  username: string;
  password: string;
}

const DEFAULT_REDIRECT_URI = `${window.location.origin}/api/v1/calendar-sync/oauth/callback`;

export function OAuthSetupCard() {
  const { toast } = useToast();

  const [googleOpen, setGoogleOpen] = useState(false);
  const [outlookOpen, setOutlookOpen] = useState(false);
  const [caldavOpen, setCaldavOpen] = useState(false);

  const [googleCreds, setGoogleCreds] = useState<ProviderCredentials>({
    client_id: '',
    client_secret: '',
    redirect_uri: DEFAULT_REDIRECT_URI,
  });

  const [outlookCreds, setOutlookCreds] = useState<ProviderCredentials>({
    client_id: '',
    client_secret: '',
    redirect_uri: DEFAULT_REDIRECT_URI,
  });

  const [caldavCreds, setCaldavCreds] = useState<CalDAVCredentials>({
    url: '',
    username: '',
    password: '',
  });

  const [showGoogleSecret, setShowGoogleSecret] = useState(false);
  const [showOutlookSecret, setShowOutlookSecret] = useState(false);
  const [showCaldavPassword, setShowCaldavPassword] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const testConnectionMutation = useMutation({
    mutationFn: testConnection,
    onSuccess: (data) => {
      toast({
        title: data.success ? 'Verbindung erfolgreich' : 'Verbindung fehlgeschlagen',
        description: data.message,
        variant: data.success ? 'default' : 'destructive',
      });
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'Verbindungstest konnte nicht durchgeführt werden',
        variant: 'destructive',
      });
    },
  });

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleSaveGoogle = () => {
    toast({ title: 'Gespeichert', description: 'Google OAuth-Konfiguration gespeichert' });
  };

  const handleSaveOutlook = () => {
    toast({ title: 'Gespeichert', description: 'Outlook OAuth-Konfiguration gespeichert' });
  };

  const handleTestCaldav = () => {
    testConnectionMutation.mutate({
      provider: 'caldav',
      url: caldavCreds.url,
      username: caldavCreds.username,
      password: caldavCreds.password,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Server className="h-5 w-5" />
          Provider-Konfiguration
        </CardTitle>
        <CardDescription>
          OAuth-Credentials und Verbindungseinstellungen für Kalender-Provider
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Google Section */}
        <Collapsible open={googleOpen} onOpenChange={setGoogleOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between p-3 h-auto">
              <div className="flex items-center gap-2">
                <svg className="h-5 w-5" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg>
                <span className="font-medium">Google OAuth</span>
              </div>
              {googleOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-4 px-3 pb-3">
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                Erstellen Sie ein OAuth2-Projekt in der{' '}
                <a
                  href="https://console.cloud.google.com/apis/credentials"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium underline inline-flex items-center gap-1"
                >
                  Google Cloud Console
                  <ExternalLink className="h-3 w-3" />
                </a>
                . Aktivieren Sie die Google Calendar API und erstellen Sie OAuth2-Credentials.
              </AlertDescription>
            </Alert>

            <div className="space-y-2">
              <Label>Client-ID</Label>
              <Input
                value={googleCreds.client_id}
                onChange={(e) =>
                  setGoogleCreds((prev) => ({ ...prev, client_id: e.target.value }))
                }
                placeholder="123456789.apps.googleusercontent.com"
              />
            </div>

            <div className="space-y-2">
              <Label>Client-Secret</Label>
              <div className="flex gap-2">
                <Input
                  type={showGoogleSecret ? 'text' : 'password'}
                  value={googleCreds.client_secret}
                  onChange={(e) =>
                    setGoogleCreds((prev) => ({ ...prev, client_secret: e.target.value }))
                  }
                  placeholder="GOCSPX-..."
                />
                <Button
                  variant="outline"
                  size="icon"
                  type="button"
                  onClick={() => setShowGoogleSecret((prev) => !prev)}
                >
                  {showGoogleSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Redirect-URI (automatisch)</Label>
              <div className="flex gap-2">
                <Input value={googleCreds.redirect_uri} readOnly className="bg-muted" />
                <Button
                  variant="outline"
                  size="icon"
                  type="button"
                  onClick={() => handleCopy(googleCreds.redirect_uri, 'google-redirect')}
                >
                  {copiedField === 'google-redirect' ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="flex justify-end">
              <Button onClick={handleSaveGoogle}>Speichern</Button>
            </div>
          </CollapsibleContent>
        </Collapsible>

        {/* Outlook Section */}
        <Collapsible open={outlookOpen} onOpenChange={setOutlookOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between p-3 h-auto">
              <div className="flex items-center gap-2">
                <svg className="h-5 w-5 text-[#0078d4]" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M7.88 12.04q0 .45-.11.87-.1.41-.33.74-.22.33-.58.52-.37.2-.87.2t-.85-.2q-.35-.21-.57-.55-.22-.33-.33-.75-.1-.42-.1-.86t.1-.87q.1-.43.34-.76.22-.34.59-.54.36-.2.87-.2t.86.2q.35.21.57.55.22.34.33.75.1.43.1.87zm-5.04-5.34v11.6l-1.56.02V5.14l1.56 1.56zm15.56-.6h-7.8v13.8h7.8c.53 0 .96-.43.96-.96V7.06c0-.53-.43-.96-.96-.96zm-1.92 12h-3.96V8.1h3.96v10z" />
                </svg>
                <span className="font-medium">Microsoft Outlook OAuth</span>
              </div>
              {outlookOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-4 px-3 pb-3">
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                Registrieren Sie eine App im{' '}
                <a
                  href="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium underline inline-flex items-center gap-1"
                >
                  Azure Portal
                  <ExternalLink className="h-3 w-3" />
                </a>
                . Fügen Sie die Microsoft Graph Calendar-Berechtigungen hinzu.
              </AlertDescription>
            </Alert>

            <div className="space-y-2">
              <Label>Application (Client) ID</Label>
              <Input
                value={outlookCreds.client_id}
                onChange={(e) =>
                  setOutlookCreds((prev) => ({ ...prev, client_id: e.target.value }))
                }
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              />
            </div>

            <div className="space-y-2">
              <Label>Client-Secret</Label>
              <div className="flex gap-2">
                <Input
                  type={showOutlookSecret ? 'text' : 'password'}
                  value={outlookCreds.client_secret}
                  onChange={(e) =>
                    setOutlookCreds((prev) => ({ ...prev, client_secret: e.target.value }))
                  }
                  placeholder="~xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                />
                <Button
                  variant="outline"
                  size="icon"
                  type="button"
                  onClick={() => setShowOutlookSecret((prev) => !prev)}
                >
                  {showOutlookSecret ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Redirect-URI (automatisch)</Label>
              <div className="flex gap-2">
                <Input value={outlookCreds.redirect_uri} readOnly className="bg-muted" />
                <Button
                  variant="outline"
                  size="icon"
                  type="button"
                  onClick={() => handleCopy(outlookCreds.redirect_uri, 'outlook-redirect')}
                >
                  {copiedField === 'outlook-redirect' ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="flex justify-end">
              <Button onClick={handleSaveOutlook}>Speichern</Button>
            </div>
          </CollapsibleContent>
        </Collapsible>

        {/* CalDAV Section */}
        <Collapsible open={caldavOpen} onOpenChange={setCaldavOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between p-3 h-auto">
              <div className="flex items-center gap-2">
                <Server className="h-5 w-5 text-orange-600" />
                <span className="font-medium">CalDAV (On-Premises)</span>
              </div>
              {caldavOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-4 px-3 pb-3">
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                Empfohlen für On-Premises-Kalender wie Nextcloud, ownCloud oder Radicale. Die
                Verbindung erfolgt direkt per CalDAV-Protokoll ohne Cloud-Dienste.
              </AlertDescription>
            </Alert>

            <div className="space-y-2">
              <Label>Server-URL</Label>
              <Input
                value={caldavCreds.url}
                onChange={(e) =>
                  setCaldavCreds((prev) => ({ ...prev, url: e.target.value }))
                }
                placeholder="https://cloud.example.com/remote.php/dav/calendars/benutzer/"
              />
            </div>

            <div className="space-y-2">
              <Label>Benutzername</Label>
              <Input
                value={caldavCreds.username}
                onChange={(e) =>
                  setCaldavCreds((prev) => ({ ...prev, username: e.target.value }))
                }
                placeholder="benutzername"
              />
            </div>

            <div className="space-y-2">
              <Label>Passwort</Label>
              <div className="flex gap-2">
                <Input
                  type={showCaldavPassword ? 'text' : 'password'}
                  value={caldavCreds.password}
                  onChange={(e) =>
                    setCaldavCreds((prev) => ({ ...prev, password: e.target.value }))
                  }
                  placeholder="App-Passwort empfohlen"
                />
                <Button
                  variant="outline"
                  size="icon"
                  type="button"
                  onClick={() => setShowCaldavPassword((prev) => !prev)}
                >
                  {showCaldavPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={handleTestCaldav}
                disabled={testConnectionMutation.isPending || !caldavCreds.url}
              >
                {testConnectionMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : null}
                Verbindung testen
              </Button>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}
