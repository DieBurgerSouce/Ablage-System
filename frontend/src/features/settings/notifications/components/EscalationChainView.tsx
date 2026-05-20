/**
 * EscalationChainView Component
 *
 * Visualisiert die Eskalationskette für nicht-beantwortete Benachrichtigungen.
 */

import {
  ArrowRight,
  Mail,
  Hash,
  Users,
  Bell,
  Smartphone,
  MessageCircle,
  Clock,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { EscalationStep, NotificationChannel, NotificationPreferences } from '../types';
import { CHANNEL_LABELS } from '../types';

interface EscalationChainViewProps {
  /** Eskalationsstufen (alternative Prop-Name: steps) */
  escalationChain?: EscalationStep[];
  /** Legacy prop name for escalationChain */
  steps?: EscalationStep[];
  /** Benachrichtigungs-Praeferenzen */
  preferences?: NotificationPreferences;
  /** Ob die Komponente deaktiviert ist */
  disabled?: boolean;
  /** Legacy prop - wird durch !disabled ersetzt */
  enabled?: boolean;
}

const CHANNEL_ICONS: Record<NotificationChannel, React.ElementType> = {
  email: Mail,
  slack: Hash,
  teams: Users,
  push: Bell,
  sms: Smartphone,
  whatsapp: MessageCircle,
  in_app: Clock,
  websocket: Clock,
};

export function EscalationChainView({
  escalationChain,
  steps: legacySteps,
  preferences,
  disabled,
  enabled,
}: EscalationChainViewProps) {
  // Support both prop interfaces
  const steps = escalationChain ?? legacySteps ?? [];
  const isEnabled = enabled ?? !disabled ?? true;

  if (!isEnabled) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-8 text-center text-muted-foreground">
          <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-yellow-500" />
          <p>Eskalationskette ist deaktiviert.</p>
          <p className="text-sm mt-1">
            Aktivieren Sie die Eskalation in den Einstellungen, um bei ausbleibender
            Reaktion automatisch über weitere Kanäle benachrichtigt zu werden.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Eskalationskette</CardTitle>
        <CardDescription>
          Bei ausbleibender Reaktion werden Sie automatisch über weitere Kanäle
          benachrichtigt. Die Eskalation stoppt, sobald Sie reagieren.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {steps.map((step, index) => (
            <div key={step.level} className="relative">
              {/* Verbindungslinie */}
              {index < steps.length - 1 && (
                <div className="absolute left-5 top-12 bottom-0 w-0.5 bg-border" />
              )}

              <div className="flex items-start gap-4">
                {/* Level Badge */}
                <div className="shrink-0">
                  <div
                    className={`
                      w-10 h-10 rounded-full flex items-center justify-center
                      font-semibold text-sm
                      ${
                        step.level <= 2
                          ? 'bg-blue-100 text-blue-700'
                          : step.level <= 4
                          ? 'bg-orange-100 text-orange-700'
                          : 'bg-red-100 text-red-700'
                      }
                    `}
                  >
                    L{step.level}
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-medium">Stufe {step.level}</span>
                    <Badge variant="outline" className="text-xs">
                      <Clock className="h-3 w-3 mr-1" />
                      {step.delayMinutes === 0
                        ? 'Sofort'
                        : `Nach ${step.delayMinutes} Min.`}
                    </Badge>
                  </div>

                  {/* Channels */}
                  <div className="flex flex-wrap gap-2">
                    {step.channels.map((channel, channelIndex) => {
                      const Icon = CHANNEL_ICONS[channel];
                      return (
                        <TooltipProvider key={channel}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div className="flex items-center">
                                <div
                                  className={`
                                    flex items-center gap-1 px-2 py-1 rounded-md text-xs
                                    ${
                                      step.level <= 2
                                        ? 'bg-blue-50 text-blue-700'
                                        : step.level <= 4
                                        ? 'bg-orange-50 text-orange-700'
                                        : 'bg-red-50 text-red-700'
                                    }
                                  `}
                                >
                                  <Icon className="h-3 w-3" />
                                  <span className="hidden sm:inline">
                                    {CHANNEL_LABELS[channel].split(' ')[0]}
                                  </span>
                                </div>
                                {channelIndex < step.channels.length - 1 && (
                                  <ArrowRight className="h-3 w-3 mx-1 text-muted-foreground" />
                                )}
                              </div>
                            </TooltipTrigger>
                            <TooltipContent>
                              {CHANNEL_LABELS[channel]}
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      );
                    })}
                  </div>

                  {/* Description */}
                  <p className="text-sm text-muted-foreground mt-1">
                    {step.description}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Footer Info */}
        <div className="mt-6 pt-4 border-t text-sm text-muted-foreground">
          <p>
            <strong>Hinweis:</strong> Die Eskalation wird automatisch gestoppt,
            sobald Sie auf eine Benachrichtigung reagieren (z.B. als gelesen
            markieren oder bestätigen).
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export default EscalationChainView;
