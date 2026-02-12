import { useSessionResume } from '@/hooks/use-session-resume';
import { AnimatedCard } from '@/components/animations';
import { CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ArrowRight, Clock, X } from 'lucide-react';
import { useNavigate } from '@tanstack/react-router';

const ROUTE_LABELS: Record<string, string> = {
  '/kunden': 'Kunden',
  '/lieferanten': 'Lieferanten',
  '/documents': 'Dokumente',
  '/banking': 'Banking',
  '/berichte': 'Berichte',
  '/search': 'Suche',
  '/vertraege': 'Verträge',
  '/workflows': 'Workflows',
  '/approvals': 'Freigaben',
  '/admin': 'Administration',
  '/settings': 'Einstellungen',
  '/scan': 'Scannen',
  '/email-import': 'E-Mail-Import',
  '/chat': 'KI-Chat',
};

function getRouteLabel(path: string): string {
  if (ROUTE_LABELS[path]) return ROUTE_LABELS[path];
  const prefix = Object.keys(ROUTE_LABELS).find(
    (key) => path.startsWith(key + '/') || path.startsWith(key + '.')
  );
  return prefix ? ROUTE_LABELS[prefix] : path;
}

function formatRelativeTime(date: Date): string {
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'gerade eben';
  if (diffMin < 60) return `vor ${diffMin} Minuten`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `vor ${diffHours} Stunde${diffHours > 1 ? 'n' : ''}`;
  return 'vor mehr als 24 Stunden';
}

export function ContinueWhereYouLeftOff() {
  const { lastRoute, lastVisitedAt, clearSession, isResumeAvailable } = useSessionResume();
  const navigate = useNavigate();

  if (!isResumeAvailable || !lastRoute) return null;

  const label = getRouteLabel(lastRoute);
  const timeAgo = lastVisitedAt ? formatRelativeTime(lastVisitedAt) : '';

  return (
    <AnimatedCard>
      <CardContent className="flex items-center gap-3 p-3">
        <Clock className="size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">Weiter wo Sie aufgehört haben</p>
          <p className="truncate text-xs text-muted-foreground">
            {label} &middot; {timeAgo}
          </p>
        </div>
        <Button
          size="sm"
          className="shrink-0 gap-1"
          onClick={() => navigate({ to: lastRoute })}
        >
          Fortsetzen
          <ArrowRight className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 shrink-0 text-muted-foreground"
          onClick={clearSession}
        >
          <X className="size-3.5" />
          <span className="sr-only">Schließen</span>
        </Button>
      </CardContent>
    </AnimatedCard>
  );
}
