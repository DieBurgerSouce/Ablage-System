/**
 * ChannelToggle Component
 *
 * Toggle für einzelne Benachrichtigungskanaele mit Status-Anzeige.
 */

import { useState } from 'react';
import {
  Mail,
  Hash,
  Users,
  Bell,
  Smartphone,
  MessageCircle,
  Inbox,
  Zap,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Settings,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { NotificationChannel, ChannelConfig } from '../types';
import { CHANNEL_LABELS } from '../types';

interface ChannelToggleProps {
  channel: ChannelConfig;
  onToggle: (channel: NotificationChannel, enabled: boolean) => void;
  onTest?: (channel: NotificationChannel) => void;
  onConfigure?: (channel: NotificationChannel) => void;
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

export function ChannelToggle({
  channel,
  onToggle,
  onTest,
  onConfigure,
  isLoading = false,
  disabled = false,
}: ChannelToggleProps) {
  const [localEnabled, setLocalEnabled] = useState(channel.enabled);
  const Icon = CHANNEL_ICONS[channel.channel];

  const handleToggle = (checked: boolean) => {
    setLocalEnabled(checked);
    onToggle(channel.channel, checked);
  };

  const showGdprWarning = channel.gdprRequired && !channel.enabled;
  const showNotConfigured = !channel.configured && channel.channel !== 'in_app' && channel.channel !== 'websocket';

  return (
    <Card className={`transition-all ${localEnabled ? 'border-primary/50' : 'border-muted'}`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-4">
          {/* Icon und Label */}
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div
              className={`p-2 rounded-lg ${
                localEnabled
                  ? 'bg-primary/10 text-primary'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              <Icon className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium truncate">
                  {CHANNEL_LABELS[channel.channel]}
                </span>
                {channel.configured ? (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      </TooltipTrigger>
                      <TooltipContent>Konfiguriert</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : showNotConfigured ? (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <XCircle className="h-4 w-4 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent>Nicht konfiguriert</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ) : null}
              </div>
              <p className="text-sm text-muted-foreground truncate">
                {channel.description}
              </p>
            </div>
          </div>

          {/* Badges und Actions */}
          <div className="flex items-center gap-2 shrink-0">
            {channel.gdprRequired && (
              <Badge variant="outline" className="text-xs">
                DSGVO
              </Badge>
            )}

            {showGdprWarning && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <AlertTriangle className="h-4 w-4 text-yellow-500" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p>
                      Für diesen Kanal ist eine explizite DSGVO-Einwilligung
                      erforderlich. Sie werden nach Aktivierung aufgefordert,
                      der Verarbeitung zuzustimmen.
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}

            {showNotConfigured && onConfigure && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onConfigure(channel.channel)}
                disabled={disabled || isLoading}
              >
                <Settings className="h-4 w-4 mr-1" />
                Einrichten
              </Button>
            )}

            {channel.configured && onTest && localEnabled && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onTest(channel.channel)}
                disabled={disabled || isLoading}
              >
                Test
              </Button>
            )}

            <Switch
              checked={localEnabled}
              onCheckedChange={handleToggle}
              disabled={disabled || isLoading || (showNotConfigured && !channel.configured)}
              aria-label={`${CHANNEL_LABELS[channel.channel]} ${localEnabled ? 'deaktivieren' : 'aktivieren'}`}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default ChannelToggle;
