/**
 * TeamActivityFeed Component
 *
 * Zeigt die Aktivitäten eines Teams als Timeline an.
 */

import { useRef, useCallback } from 'react';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  UserPlus,
  UserMinus,
  Shield,
  FileText,
  Mail,
  Check,
  X,
  Archive,
  Settings,
  Plus,
  Activity,
  Loader2,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';
import { TeamActivity, TeamActivityType } from '../api/teams-api';
import { useTeamActivityInfinite } from '../hooks/use-teams';

interface TeamActivityFeedProps {
  teamId: string;
}

const activityConfig: Record<
  TeamActivityType,
  { icon: React.ElementType; color: string; getMessage: (activity: TeamActivity) => string }
> = {
  member_added: {
    icon: UserPlus,
    color: 'text-green-600 bg-green-100 dark:bg-green-900',
    getMessage: (a) =>
      `${a.actor?.full_name || a.actor?.username || 'Jemand'} hat ${
        a.target_user?.full_name || a.target_user?.username || 'ein Mitglied'
      } zum Team hinzugefügt`,
  },
  member_removed: {
    icon: UserMinus,
    color: 'text-red-600 bg-red-100 dark:bg-red-900',
    getMessage: (a) =>
      `${a.actor?.full_name || a.actor?.username || 'Jemand'} hat ${
        a.target_user?.full_name || a.target_user?.username || 'ein Mitglied'
      } aus dem Team entfernt`,
  },
  member_role_changed: {
    icon: Shield,
    color: 'text-blue-600 bg-blue-100 dark:bg-blue-900',
    getMessage: (a) => {
      const newRole = (a.details?.new_role as string) || 'unbekannt';
      return `Rolle von ${a.target_user?.full_name || a.target_user?.username || 'Mitglied'} wurde zu "${newRole}" geändert`;
    },
  },
  team_created: {
    icon: Plus,
    color: 'text-green-600 bg-green-100 dark:bg-green-900',
    getMessage: (a) =>
      `${a.actor?.full_name || a.actor?.username || 'Jemand'} hat das Team erstellt`,
  },
  team_updated: {
    icon: Settings,
    color: 'text-blue-600 bg-blue-100 dark:bg-blue-900',
    getMessage: (a) =>
      `${a.actor?.full_name || a.actor?.username || 'Jemand'} hat die Team-Einstellungen aktualisiert`,
  },
  team_archived: {
    icon: Archive,
    color: 'text-orange-600 bg-orange-100 dark:bg-orange-900',
    getMessage: (a) =>
      `${a.actor?.full_name || a.actor?.username || 'Jemand'} hat das Team archiviert`,
  },
  document_shared: {
    icon: FileText,
    color: 'text-purple-600 bg-purple-100 dark:bg-purple-900',
    getMessage: (a) =>
      `${a.actor?.full_name || a.actor?.username || 'Jemand'} hat ein Dokument mit dem Team geteilt`,
  },
  document_unshared: {
    icon: FileText,
    color: 'text-gray-600 bg-gray-100 dark:bg-gray-800',
    getMessage: (a) =>
      `${a.actor?.full_name || a.actor?.username || 'Jemand'} hat die Freigabe eines Dokuments aufgehoben`,
  },
  invitation_sent: {
    icon: Mail,
    color: 'text-blue-600 bg-blue-100 dark:bg-blue-900',
    getMessage: (a) => {
      const email = (a.details?.email as string) || 'jemanden';
      return `Einladung an ${email} wurde gesendet`;
    },
  },
  invitation_accepted: {
    icon: Check,
    color: 'text-green-600 bg-green-100 dark:bg-green-900',
    getMessage: (a) =>
      `${a.target_user?.full_name || a.target_user?.username || 'Jemand'} hat die Einladung angenommen`,
  },
  invitation_declined: {
    icon: X,
    color: 'text-red-600 bg-red-100 dark:bg-red-900',
    getMessage: (a) => {
      const email = (a.details?.email as string) || 'Jemand';
      return `${email} hat die Einladung abgelehnt`;
    },
  },
};

export function TeamActivityFeed({ teamId }: TeamActivityFeedProps) {
  const { data, isLoading, hasNextPage, fetchNextPage, isFetchingNextPage } =
    useTeamActivityInfinite(teamId, { page_size: 20 });

  const observer = useRef<IntersectionObserver | null>(null);
  const lastActivityRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (isFetchingNextPage) return;
      if (observer.current) observer.current.disconnect();
      observer.current = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && hasNextPage) {
          fetchNextPage();
        }
      });
      if (node) observer.current.observe(node);
    },
    [isFetchingNextPage, hasNextPage, fetchNextPage]
  );

  const activities = data?.pages.flatMap((page) => page.activities) ?? [];

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="h-8 w-8 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (activities.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Activity className="h-12 w-12 mx-auto mb-2 opacity-50" />
        <p>Keine Aktivitäten</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {activities.map((activity, index) => {
        const config = activityConfig[activity.activity_type];
        const Icon = config.icon;
        const isLast = index === activities.length - 1;

        return (
          <div
            key={activity.id}
            ref={isLast ? lastActivityRef : undefined}
            className="flex gap-3"
          >
            <div className={`p-2 rounded-full h-fit ${config.color}`}>
              <Icon className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm">{config.getMessage(activity)}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {formatDistanceToNow(new Date(activity.created_at), {
                  addSuffix: true,
                  locale: de,
                })}
              </p>
            </div>
          </div>
        );
      })}

      {isFetchingNextPage && (
        <div className="flex justify-center py-4">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {hasNextPage && !isFetchingNextPage && (
        <div className="flex justify-center">
          <Button variant="ghost" size="sm" onClick={() => fetchNextPage()}>
            Mehr laden
          </Button>
        </div>
      )}
    </div>
  );
}
