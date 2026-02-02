/**
 * NotificationTypeToggle Component
 *
 * Toggle-Komponente fuer einzelne Benachrichtigungstypen.
 * Ermoeglicht Opt-in/Opt-out pro Benachrichtigungskategorie.
 */

import { useState } from 'react';
import {
  FileText,
  AlertTriangle,
  Workflow,
  Server,
  Shield,
  DollarSign,
  Scale,
  Clock,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import type { NotificationCategory, NotificationChannel } from '../types';
import { CATEGORY_LABELS, CHANNEL_LABELS } from '../types';

interface NotificationTypeConfig {
  category: NotificationCategory;
  enabled: boolean;
  channels: NotificationChannel[];
  description: string;
}

interface NotificationTypeToggleProps {
  config: NotificationTypeConfig;
  availableChannels: NotificationChannel[];
  onChange: (category: NotificationCategory, enabled: boolean, channels: NotificationChannel[]) => void;
  disabled?: boolean;
}

const CATEGORY_ICONS: Record<NotificationCategory, React.ElementType> = {
  document: FileText,
  alert: AlertTriangle,
  workflow: Workflow,
  system: Server,
  security: Shield,
  finance: DollarSign,
  compliance: Scale,
  reminder: Clock,
};

const CATEGORY_DESCRIPTIONS: Record<NotificationCategory, string> = {
  document: 'Benachrichtigungen zu Dokumenten-Upload, OCR-Verarbeitung und Freigaben',
  alert: 'Warnungen und kritische Hinweise, die Ihre Aufmerksamkeit erfordern',
  workflow: 'Status-Updates zu Workflows, Genehmigungen und Aufgaben',
  system: 'Systemmeldungen, Updates und technische Benachrichtigungen',
  security: 'Sicherheitsrelevante Ereignisse wie Login-Versuche und Zugriffsaenderungen',
  finance: 'Finanzielle Benachrichtigungen zu Rechnungen, Zahlungen und Fristen',
  compliance: 'Compliance-bezogene Meldungen und regulatorische Hinweise',
  reminder: 'Erinnerungen an Fristen, Termine und ausstehende Aufgaben',
};

export function NotificationTypeToggle({
  config,
  availableChannels,
  onChange,
  disabled = false,
}: NotificationTypeToggleProps) {
  const [isOpen, setIsOpen] = useState(false);

  const Icon = CATEGORY_ICONS[config.category];
  const description = CATEGORY_DESCRIPTIONS[config.category] || config.description;

  const handleToggle = (enabled: boolean) => {
    onChange(config.category, enabled, config.channels);
  };

  const handleChannelToggle = (channel: NotificationChannel, checked: boolean) => {
    const newChannels = checked
      ? [...config.channels, channel]
      : config.channels.filter((c) => c !== channel);
    onChange(config.category, config.enabled, newChannels);
  };

  const activeChannelsCount = config.channels.length;

  return (
    <Card className={config.enabled ? 'border-primary/30' : ''}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div
              className={`
                p-2 rounded-lg shrink-0
                ${config.enabled ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'}
              `}
            >
              <Icon className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium truncate">
                  {CATEGORY_LABELS[config.category]}
                </span>
                {activeChannelsCount > 0 && config.enabled && (
                  <span className="text-xs text-muted-foreground">
                    ({activeChannelsCount} {activeChannelsCount === 1 ? 'Kanal' : 'Kanaele'})
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground truncate">{description}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Switch
              checked={config.enabled}
              onCheckedChange={handleToggle}
              disabled={disabled}
              aria-label={`${CATEGORY_LABELS[config.category]} aktivieren/deaktivieren`}
            />
          </div>
        </div>

        {config.enabled && (
          <Collapsible open={isOpen} onOpenChange={setIsOpen}>
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="w-full mt-3 justify-between text-muted-foreground hover:text-foreground"
              >
                <span>Kanaele konfigurieren</span>
                {isOpen ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-3 pt-3 border-t space-y-3">
                <p className="text-sm text-muted-foreground">
                  Waehlen Sie die Kanaele aus, ueber die Sie diese Benachrichtigungen erhalten moechten:
                </p>
                <div className="grid grid-cols-2 gap-3">
                  {availableChannels.map((channel) => (
                    <div key={channel} className="flex items-center space-x-2">
                      <Checkbox
                        id={`${config.category}-${channel}`}
                        checked={config.channels.includes(channel)}
                        onCheckedChange={(checked) =>
                          handleChannelToggle(channel, checked === true)
                        }
                        disabled={disabled}
                      />
                      <Label
                        htmlFor={`${config.category}-${channel}`}
                        className="text-sm cursor-pointer"
                      >
                        {CHANNEL_LABELS[channel]}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardContent>
    </Card>
  );
}

interface NotificationTypesListProps {
  configs: NotificationTypeConfig[];
  availableChannels: NotificationChannel[];
  onChange: (category: NotificationCategory, enabled: boolean, channels: NotificationChannel[]) => void;
  disabled?: boolean;
}

export function NotificationTypesList({
  configs,
  availableChannels,
  onChange,
  disabled = false,
}: NotificationTypesListProps) {
  return (
    <div className="space-y-3">
      {configs.map((config) => (
        <NotificationTypeToggle
          key={config.category}
          config={config}
          availableChannels={availableChannels}
          onChange={onChange}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

export default NotificationTypeToggle;
