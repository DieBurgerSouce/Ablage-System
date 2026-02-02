/**
 * LeaderboardTable Component
 *
 * Zeigt das Top-10 Leaderboard mit Rang, Punkte, Streak und Achievements.
 * Unterstuetzt verschiedene Zeitraeume (Woche, Monat, Gesamt).
 */

import { Trophy, Medal, Award, Star, Crown, User } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { StreakBadge } from './StreakBadge';
import { useLeaderboard, type LeaderboardPeriod } from '../hooks/use-ocr-feedback';
import type { LeaderboardEntry } from '../api/ocr-feedback-api';
import { useState } from 'react';

interface LeaderboardTableProps {
  className?: string;
}

function getRankIcon(rank: number) {
  switch (rank) {
    case 1:
      return <Crown className="w-5 h-5 text-yellow-500" />;
    case 2:
      return <Medal className="w-5 h-5 text-gray-400" />;
    case 3:
      return <Award className="w-5 h-5 text-amber-600" />;
    default:
      return (
        <span className="w-5 h-5 flex items-center justify-center text-sm font-medium text-muted-foreground">
          {rank}
        </span>
      );
  }
}

function getRankBadgeStyle(rank: number): string {
  switch (rank) {
    case 1:
      return 'bg-gradient-to-r from-yellow-400 to-yellow-600 text-white border-yellow-500';
    case 2:
      return 'bg-gradient-to-r from-gray-300 to-gray-400 text-gray-800 border-gray-400';
    case 3:
      return 'bg-gradient-to-r from-amber-500 to-amber-700 text-white border-amber-600';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

function LeaderboardEntryRow({ entry, showRankBadge = true }: { entry: LeaderboardEntry; showRankBadge?: boolean }) {
  const initials = entry.full_name
    ? entry.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : entry.username.slice(0, 2).toUpperCase();

  return (
    <div
      className={cn(
        'flex items-center gap-4 p-3 rounded-lg transition-colors',
        entry.is_current_user
          ? 'bg-primary/10 border border-primary/30'
          : 'hover:bg-muted/50'
      )}
    >
      {/* Rang */}
      <div className="flex-shrink-0 w-8 flex items-center justify-center">
        {showRankBadge && entry.rank <= 3 ? (
          <div
            className={cn(
              'w-8 h-8 rounded-full flex items-center justify-center border',
              getRankBadgeStyle(entry.rank)
            )}
          >
            {getRankIcon(entry.rank)}
          </div>
        ) : (
          getRankIcon(entry.rank)
        )}
      </div>

      {/* Avatar & Name */}
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <Avatar className="h-10 w-10">
          <AvatarFallback className={entry.is_current_user ? 'bg-primary text-primary-foreground' : ''}>
            {initials}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium truncate">
              {entry.full_name || entry.username}
            </span>
            {entry.is_current_user && (
              <Badge variant="secondary" className="text-xs">Du</Badge>
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {entry.corrections_count} Korrekturen
          </div>
        </div>
      </div>

      {/* Streak */}
      <div className="flex-shrink-0">
        <StreakBadge streak={entry.current_streak} size="sm" showLabel={false} />
      </div>

      {/* Punkte */}
      <div className="flex-shrink-0 text-right">
        <div className="font-bold text-lg">
          {entry.total_points.toLocaleString('de-DE')}
        </div>
        <div className="text-xs text-muted-foreground">Punkte</div>
      </div>
    </div>
  );
}

function LeaderboardSkeleton() {
  return (
    <div className="space-y-3">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-3">
          <Skeleton className="w-8 h-8 rounded-full" />
          <Skeleton className="w-10 h-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-20" />
          </div>
          <Skeleton className="h-6 w-16" />
        </div>
      ))}
    </div>
  );
}

function LeaderboardContent({ period }: { period: LeaderboardPeriod }) {
  const { data, isLoading, error } = useLeaderboard(period, 10);

  if (isLoading) {
    return <LeaderboardSkeleton />;
  }

  if (error) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        Leaderboard konnte nicht geladen werden.
      </div>
    );
  }

  if (!data || data.entries.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <User className="w-12 h-12 mx-auto mb-3 opacity-50" />
        <p>Noch keine Korrekturen in diesem Zeitraum.</p>
        <p className="text-sm mt-1">
          Mindestens 5 Korrekturen fuer Ranking erforderlich.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {data.entries.map((entry) => (
        <LeaderboardEntryRow key={entry.user_id} entry={entry} />
      ))}
    </div>
  );
}

export function LeaderboardTable({ className }: LeaderboardTableProps) {
  const [period, setPeriod] = useState<LeaderboardPeriod>('weekly');

  const periodLabels: Record<LeaderboardPeriod, string> = {
    weekly: 'Diese Woche',
    monthly: 'Dieser Monat',
    all_time: 'Gesamt',
  };

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Trophy className="w-5 h-5 text-yellow-500" />
            <CardTitle>Leaderboard</CardTitle>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs value={period} onValueChange={(v) => setPeriod(v as LeaderboardPeriod)}>
          <TabsList className="w-full mb-4">
            <TabsTrigger value="weekly" className="flex-1">Woche</TabsTrigger>
            <TabsTrigger value="monthly" className="flex-1">Monat</TabsTrigger>
            <TabsTrigger value="all_time" className="flex-1">Gesamt</TabsTrigger>
          </TabsList>

          <TabsContent value="weekly">
            <LeaderboardContent period="weekly" />
          </TabsContent>
          <TabsContent value="monthly">
            <LeaderboardContent period="monthly" />
          </TabsContent>
          <TabsContent value="all_time">
            <LeaderboardContent period="all_time" />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
