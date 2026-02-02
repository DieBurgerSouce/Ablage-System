/**
 * UserStatsCard Component
 *
 * Zeigt die eigenen Statistiken des Benutzers.
 * Punkte, Streak, Rank und Achievements.
 */

import { Target, TrendingUp, Star, Award, Zap, Trophy, Medal, Crown, Diamond, Flame } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { StreakBadge } from './StreakBadge';
import { useUserStats } from '../hooks/use-ocr-feedback';

interface UserStatsCardProps {
  className?: string;
}

// Achievement Icon Mapping
const achievementIcons: Record<string, React.ElementType> = {
  first_correction: Star,
  correction_10: Target,
  correction_50: Award,
  correction_100: Trophy,
  points_100: Target,
  points_500: Zap,
  points_1000: Crown,
  streak_3: Flame,
  streak_7: Flame,
  streak_30: Diamond,
};

// Achievement Labels
const achievementLabels: Record<string, { name: string; description: string }> = {
  first_correction: { name: 'Erste Korrektur', description: 'Erste OCR-Korrektur eingereicht' },
  correction_10: { name: 'Fleissiger Korrektor', description: '10 Korrekturen eingereicht' },
  correction_50: { name: 'Korrektur-Experte', description: '50 Korrekturen eingereicht' },
  correction_100: { name: 'Korrektur-Meister', description: '100 Korrekturen eingereicht' },
  points_100: { name: 'Punktesammler', description: '100 Punkte erreicht' },
  points_500: { name: 'Punkte-Profi', description: '500 Punkte erreicht' },
  points_1000: { name: 'Punkte-Champion', description: '1000 Punkte erreicht' },
  streak_3: { name: 'Drei-Tage-Streak', description: '3 Tage in Folge korrigiert' },
  streak_7: { name: 'Wochen-Streak', description: '7 Tage in Folge korrigiert' },
  streak_30: { name: 'Monats-Champion', description: '30 Tage in Folge korrigiert' },
};

function StatItem({
  label,
  value,
  subValue,
  icon: Icon,
  trend,
}: {
  label: string;
  value: string | number;
  subValue?: string;
  icon?: React.ElementType;
  trend?: 'up' | 'down' | 'neutral';
}) {
  return (
    <div className="text-center p-3 rounded-lg bg-muted/50">
      {Icon && (
        <div className="flex justify-center mb-1">
          <Icon className="w-4 h-4 text-muted-foreground" />
        </div>
      )}
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
      {subValue && (
        <div
          className={cn(
            'text-xs mt-1',
            trend === 'up' && 'text-green-500',
            trend === 'down' && 'text-red-500',
            trend === 'neutral' && 'text-muted-foreground'
          )}
        >
          {subValue}
        </div>
      )}
    </div>
  );
}

function UserStatsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="p-3 rounded-lg bg-muted/50 text-center">
            <Skeleton className="h-4 w-4 mx-auto mb-2" />
            <Skeleton className="h-8 w-16 mx-auto" />
            <Skeleton className="h-3 w-12 mx-auto mt-1" />
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <div className="flex gap-2">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-8 w-8 rounded-full" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function UserStatsCard({ className }: UserStatsCardProps) {
  const { data: stats, isLoading, error } = useUserStats();

  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Target className="w-5 h-5" />
            Meine Statistiken
          </CardTitle>
        </CardHeader>
        <CardContent>
          <UserStatsSkeleton />
        </CardContent>
      </Card>
    );
  }

  if (error || !stats) {
    return (
      <Card className={className}>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Target className="w-5 h-5" />
            Meine Statistiken
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-muted-foreground">
            Statistiken konnten nicht geladen werden.
          </div>
        </CardContent>
      </Card>
    );
  }

  // Naechstes Achievement berechnen
  const nextMilestones = {
    corrections: [10, 50, 100],
    points: [100, 500, 1000],
    streak: [3, 7, 30],
  };

  const nextCorrectionMilestone = nextMilestones.corrections.find(m => m > stats.total_corrections) || 100;
  const correctionProgress = Math.min((stats.total_corrections / nextCorrectionMilestone) * 100, 100);

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Target className="w-5 h-5" />
            Meine Statistiken
          </CardTitle>
          <StreakBadge streak={stats.current_streak} size="md" />
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Haupt-Statistiken */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatItem
            label="Punkte"
            value={stats.total_points.toLocaleString('de-DE')}
            icon={Star}
            subValue={`+${stats.weekly_points} diese Woche`}
            trend={stats.weekly_points > 0 ? 'up' : 'neutral'}
          />
          <StatItem
            label="Korrekturen"
            value={stats.total_corrections}
            icon={Target}
            subValue={`${stats.weekly_corrections} diese Woche`}
            trend={stats.weekly_corrections > 0 ? 'up' : 'neutral'}
          />
          <StatItem
            label="Wochen-Rang"
            value={stats.weekly_rank ? `#${stats.weekly_rank}` : '-'}
            icon={Trophy}
            subValue={stats.monthly_rank ? `Monat: #${stats.monthly_rank}` : 'Monat: -'}
          />
          <StatItem
            label="Genauigkeit"
            value={`${Math.round(stats.accuracy_rate * 100)}%`}
            icon={TrendingUp}
            subValue={`Laengster Streak: ${stats.longest_streak} Tage`}
          />
        </div>

        {/* Fortschritt zum naechsten Achievement */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Naechstes Ziel: {nextCorrectionMilestone} Korrekturen</span>
            <span className="font-medium">{stats.total_corrections}/{nextCorrectionMilestone}</span>
          </div>
          <Progress value={correctionProgress} className="h-2" />
        </div>

        {/* Achievements */}
        {stats.achievements.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">Achievements</h4>
            <TooltipProvider>
              <div className="flex flex-wrap gap-2">
                {stats.achievements.map((achievement) => {
                  const Icon = achievementIcons[achievement] || Star;
                  const label = achievementLabels[achievement];
                  return (
                    <Tooltip key={achievement}>
                      <TooltipTrigger asChild>
                        <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center border border-primary/30 cursor-help">
                          <Icon className="w-5 h-5 text-primary" />
                        </div>
                      </TooltipTrigger>
                      <TooltipContent>
                        <div className="font-medium">{label?.name || achievement}</div>
                        <div className="text-xs text-muted-foreground">{label?.description}</div>
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </div>
            </TooltipProvider>
          </div>
        )}

        {/* Punkte-Aufschluesselung */}
        {Object.keys(stats.points_breakdown).length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">Punkte nach Typ</h4>
            <div className="flex flex-wrap gap-2">
              {Object.entries(stats.points_breakdown).map(([type, points]) => (
                <Badge key={type} variant="secondary">
                  {type}: {points.toLocaleString('de-DE')}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
