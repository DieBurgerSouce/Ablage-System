/**
 * SeverityMatrix Component
 *
 * Matrix-Darstellung: Welcher Kanal bei welchem Schweregrad aktiv ist.
 */

import { useState, useEffect } from 'react';
import {
  Mail,
  Hash,
  Users,
  Bell,
  Smartphone,
  MessageCircle,
  Inbox,
  Zap,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type {
  NotificationChannel,
  NotificationSeverity,
  NotificationPreferences,
} from '../types';
import {
  CHANNEL_LABELS,
  SEVERITY_LABELS,
  SEVERITY_COLORS,
} from '../types';

interface SeverityMatrixProps {
  preferences: NotificationPreferences;
  onUpdate: (severity: NotificationSeverity, channels: NotificationChannel[]) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

const CHANNEL_ICONS: Record<NotificationChannel, React.ElementType> = {
  email: Mail,
  slack: Hash,
  teams: Users,
  push: Bell,
  sms: Smartphone,
  whatsapp: MessageCircle,
  in_app: Inbox,
  websocket: Zap,
};

const SEVERITIES: NotificationSeverity[] = ['info', 'low', 'medium', 'high', 'critical'];
const DISPLAY_CHANNELS: NotificationChannel[] = ['email', 'slack', 'teams', 'push', 'sms', 'in_app'];

// Standard-Kanäle pro Schweregrad (aus Backend)
const DEFAULT_CHANNELS_BY_SEVERITY: Record<NotificationSeverity, NotificationChannel[]> = {
  info: ['in_app'],
  low: ['in_app', 'websocket'],
  medium: ['email', 'slack', 'in_app'],
  high: ['email', 'slack', 'teams', 'push', 'in_app'],
  critical: ['email', 'slack', 'teams', 'push', 'sms', 'in_app'],
};

export function SeverityMatrix({
  preferences,
  onUpdate,
  isLoading = false,
  disabled = false,
}: SeverityMatrixProps) {
  // Lokaler State für die Matrix
  const [matrix, setMatrix] = useState<Record<NotificationSeverity, NotificationChannel[]>>(
    DEFAULT_CHANNELS_BY_SEVERITY
  );

  // Initialisiere Matrix basierend auf Praeferenzen
  useEffect(() => {
    const newMatrix = { ...DEFAULT_CHANNELS_BY_SEVERITY };

    // Passe basierend auf min severity an
    if (!preferences.emailEnabled) {
      Object.keys(newMatrix).forEach((sev) => {
        newMatrix[sev as NotificationSeverity] = newMatrix[sev as NotificationSeverity].filter(
          (c) => c !== 'email'
        );
      });
    }
    if (!preferences.slackEnabled) {
      Object.keys(newMatrix).forEach((sev) => {
        newMatrix[sev as NotificationSeverity] = newMatrix[sev as NotificationSeverity].filter(
          (c) => c !== 'slack'
        );
      });
    }
    if (!preferences.teamsEnabled) {
      Object.keys(newMatrix).forEach((sev) => {
        newMatrix[sev as NotificationSeverity] = newMatrix[sev as NotificationSeverity].filter(
          (c) => c !== 'teams'
        );
      });
    }
    if (!preferences.pushEnabled) {
      Object.keys(newMatrix).forEach((sev) => {
        newMatrix[sev as NotificationSeverity] = newMatrix[sev as NotificationSeverity].filter(
          (c) => c !== 'push'
        );
      });
    }
    if (!preferences.smsEnabled) {
      Object.keys(newMatrix).forEach((sev) => {
        newMatrix[sev as NotificationSeverity] = newMatrix[sev as NotificationSeverity].filter(
          (c) => c !== 'sms'
        );
      });
    }

    setMatrix(newMatrix);
  }, [preferences]);

  const handleToggle = (severity: NotificationSeverity, channel: NotificationChannel) => {
    const currentChannels = matrix[severity];
    const newChannels = currentChannels.includes(channel)
      ? currentChannels.filter((c) => c !== channel)
      : [...currentChannels, channel];

    setMatrix((prev) => ({
      ...prev,
      [severity]: newChannels,
    }));

    onUpdate(severity, newChannels);
  };

  const isChannelEnabled = (channel: NotificationChannel): boolean => {
    switch (channel) {
      case 'email':
        return preferences.emailEnabled;
      case 'slack':
        return preferences.slackEnabled;
      case 'teams':
        return preferences.teamsEnabled;
      case 'push':
        return preferences.pushEnabled;
      case 'sms':
        return preferences.smsEnabled;
      case 'in_app':
        return preferences.inAppEnabled;
      default:
        return true;
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Schweregrad-Matrix</CardTitle>
        <CardDescription>
          Legen Sie fest, über welche Kanäle Sie bei verschiedenen Schweregraden
          benachrichtigt werden möchten.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-32">Schweregrad</TableHead>
                {DISPLAY_CHANNELS.map((channel) => {
                  const Icon = CHANNEL_ICONS[channel];
                  const enabled = isChannelEnabled(channel);
                  return (
                    <TableHead
                      key={channel}
                      className={`text-center ${!enabled ? 'opacity-50' : ''}`}
                    >
                      <div className="flex flex-col items-center gap-1">
                        <Icon className="h-4 w-4" />
                        <span className="text-xs font-normal">
                          {CHANNEL_LABELS[channel].split(' ')[0]}
                        </span>
                      </div>
                    </TableHead>
                  );
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {SEVERITIES.map((severity) => (
                <TableRow key={severity}>
                  <TableCell>
                    <Badge className={SEVERITY_COLORS[severity]}>
                      {SEVERITY_LABELS[severity]}
                    </Badge>
                  </TableCell>
                  {DISPLAY_CHANNELS.map((channel) => {
                    const isActive = matrix[severity].includes(channel);
                    const channelEnabled = isChannelEnabled(channel);
                    return (
                      <TableCell key={channel} className="text-center">
                        <Checkbox
                          checked={isActive && channelEnabled}
                          onCheckedChange={() => handleToggle(severity, channel)}
                          disabled={disabled || isLoading || !channelEnabled}
                          aria-label={`${CHANNEL_LABELS[channel]} für ${SEVERITY_LABELS[severity]}`}
                        />
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="mt-4 text-sm text-muted-foreground">
          <p>
            <strong>Hinweis:</strong> Deaktivierte Kanäle (grau) müssen zuerst in der
            Kanal-Übersicht aktiviert werden.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export default SeverityMatrix;
