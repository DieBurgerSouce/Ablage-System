/**
 * GdprConsentBanner Component
 *
 * DSGVO-Hinweis für Kanäle die personenbezogene Daten verarbeiten (SMS, WhatsApp).
 */

import { useState } from 'react';
import { Shield, AlertTriangle, Check, X } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { NotificationChannel } from '../types';
import { CHANNEL_LABELS } from '../types';

interface GdprConsentBannerProps {
  channel: NotificationChannel;
  onAccept: () => void;
  onDecline: () => void;
  isLoading?: boolean;
}

export function GdprConsentBanner({
  channel,
  onAccept,
  onDecline,
  isLoading = false,
}: GdprConsentBannerProps) {
  const [showDialog, setShowDialog] = useState(false);
  const [consented, setConsented] = useState(false);

  const channelLabel = CHANNEL_LABELS[channel];

  const handleAccept = () => {
    if (consented) {
      onAccept();
      setShowDialog(false);
    }
  };

  return (
    <>
      <Alert className="border-yellow-500/50 bg-yellow-500/10">
        <Shield className="h-4 w-4 text-yellow-600" />
        <AlertTitle className="text-yellow-800">DSGVO-Einwilligung erforderlich</AlertTitle>
        <AlertDescription className="text-yellow-700">
          <p className="mb-3">
            Für {channelLabel}-Benachrichtigungen ist Ihre ausdrückliche
            Einwilligung nach DSGVO Art. 6 Abs. 1 lit. a erforderlich, da
            hierbei personenbezogene Daten (Telefonnummer) an Drittanbieter
            übermittelt werden.
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => setShowDialog(true)}
              disabled={isLoading}
            >
              <Check className="h-4 w-4 mr-1" />
              Einwilligung erteilen
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onDecline}
              disabled={isLoading}
            >
              <X className="h-4 w-4 mr-1" />
              Nicht jetzt
            </Button>
          </div>
        </AlertDescription>
      </Alert>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              DSGVO-Einwilligung: {channelLabel}
            </DialogTitle>
            <DialogDescription>
              Bitte lesen Sie die folgenden Informationen sorgfältig durch.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4 space-y-4 text-sm">
            <div>
              <h4 className="font-semibold mb-2">Datenverarbeitung</h4>
              <p className="text-muted-foreground">
                Zur Zustellung von {channelLabel}-Benachrichtigungen wird Ihre
                Telefonnummer an unseren Dienstleister Twilio Inc. (USA)
                übermittelt. Twilio ist EU-US Data Privacy Framework
                zertifiziert.
              </p>
            </div>

            <div>
              <h4 className="font-semibold mb-2">Verarbeitete Daten</h4>
              <ul className="list-disc pl-4 text-muted-foreground space-y-1">
                <li>Telefonnummer im E.164-Format</li>
                <li>Nachrichteninhalt (Titel und Text)</li>
                <li>Zustellungsstatus und Zeitstempel</li>
              </ul>
            </div>

            <div>
              <h4 className="font-semibold mb-2">Ihre Rechte</h4>
              <ul className="list-disc pl-4 text-muted-foreground space-y-1">
                <li>Widerruf jederzeit möglich (DSGVO Art. 7 Abs. 3)</li>
                <li>Auskunft über gespeicherte Daten</li>
                <li>Löschung aller verarbeiteten Daten</li>
              </ul>
            </div>

            <div className="bg-muted/50 p-3 rounded-lg">
              <div className="flex items-start gap-2">
                <Checkbox
                  id="gdpr-consent"
                  checked={consented}
                  onCheckedChange={(checked) => setConsented(checked === true)}
                />
                <Label htmlFor="gdpr-consent" className="text-sm font-normal leading-relaxed">
                  Ich willige ein, dass meine Telefonnummer zur Zustellung von
                  Benachrichtigungen an Twilio Inc. übermittelt wird. Mir ist
                  bekannt, dass ich diese Einwilligung jederzeit widerrufen kann.
                </Label>
              </div>
            </div>

            {!consented && (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  Bitte bestätigen Sie die Einwilligung, um fortzufahren.
                </AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDialog(false)}>
              Abbrechen
            </Button>
            <Button onClick={handleAccept} disabled={!consented || isLoading}>
              <Check className="h-4 w-4 mr-1" />
              Einwilligung bestätigen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default GdprConsentBanner;
