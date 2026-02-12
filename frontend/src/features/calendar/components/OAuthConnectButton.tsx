/**
 * OAuth Connect Button
 *
 * Provider-spezifischer OAuth-Verbindungsbutton mit Status-Anzeige
 * für Google und Outlook Kalender-Integration.
 */

import { useState } from 'react';
import { CheckCircle2, Loader2, LogOut, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { OAuthStatus } from '../types/calendar-types';

interface OAuthConnectButtonProps {
  provider: 'google' | 'outlook';
  status: OAuthStatus;
  onConnect: (provider: 'google' | 'outlook') => void;
  onDisconnect: (provider: 'google' | 'outlook') => void;
  isLoading?: boolean;
}

const PROVIDER_CONFIG = {
  google: {
    label: 'Google Kalender',
    connectLabel: 'Mit Google verbinden',
    bgClass: 'bg-white hover:bg-gray-50 text-gray-700 border border-gray-300',
    iconSvg: (
      <svg className="h-5 w-5 mr-2" viewBox="0 0 24 24">
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
    ),
  },
  outlook: {
    label: 'Microsoft Outlook',
    connectLabel: 'Mit Outlook verbinden',
    bgClass: 'bg-[#0078d4] hover:bg-[#006cbe] text-white',
    iconSvg: (
      <svg className="h-5 w-5 mr-2" viewBox="0 0 24 24" fill="currentColor">
        <path d="M7.88 12.04q0 .45-.11.87-.1.41-.33.74-.22.33-.58.52-.37.2-.87.2t-.85-.2q-.35-.21-.57-.55-.22-.33-.33-.75-.1-.42-.1-.86t.1-.87q.1-.43.34-.76.22-.34.59-.54.36-.2.87-.2t.86.2q.35.21.57.55.22.34.33.75.1.43.1.87zm-5.04-5.34v11.6l-1.56.02V5.14l1.56 1.56zm15.56-.6h-7.8v13.8h7.8c.53 0 .96-.43.96-.96V7.06c0-.53-.43-.96-.96-.96zm-1.92 12h-3.96V8.1h3.96v10z" />
      </svg>
    ),
  },
} as const;

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMinutes < 1) return 'gerade eben';
  if (diffMinutes < 60) return `vor ${diffMinutes} Minuten`;
  if (diffHours < 24) return `vor ${diffHours} Stunden`;
  if (diffDays < 30) return `vor ${diffDays} Tagen`;
  return date.toLocaleDateString('de-DE');
}

export function OAuthConnectButton({
  provider,
  status,
  onConnect,
  onDisconnect,
  isLoading = false,
}: OAuthConnectButtonProps) {
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const config = PROVIDER_CONFIG[provider];

  const handleDisconnect = () => {
    setIsDisconnecting(true);
    onDisconnect(provider);
    // Reset after a short delay in case the parent doesn't update immediately
    setTimeout(() => setIsDisconnecting(false), 3000);
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-3 p-4 rounded-lg border bg-muted/30">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Verbindung wird hergestellt...</span>
      </div>
    );
  }

  if (status.connected) {
    return (
      <div className="flex items-center justify-between gap-4 p-4 rounded-lg border border-green-200 bg-green-50/50">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="h-5 w-5 text-green-600 flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-green-800">
              {config.label} verbunden
            </p>
            {status.email && (
              <p className="text-xs text-green-600 truncate">{status.email}</p>
            )}
            {status.expires_at && (
              <p className="text-xs text-muted-foreground">
                Verbunden {formatRelativeTime(status.expires_at)}
              </p>
            )}
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleDisconnect}
          disabled={isDisconnecting}
          className="text-red-600 border-red-200 hover:bg-red-50 hover:text-red-700 flex-shrink-0"
        >
          {isDisconnecting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <>
              <LogOut className="h-4 w-4 mr-1" />
              Trennen
            </>
          )}
        </Button>
      </div>
    );
  }

  return (
    <Button
      onClick={() => onConnect(provider)}
      className={cn('w-full justify-center py-5', config.bgClass)}
      variant="outline"
    >
      {config.iconSvg}
      {config.connectLabel}
      <ExternalLink className="h-4 w-4 ml-2 opacity-60" />
    </Button>
  );
}
