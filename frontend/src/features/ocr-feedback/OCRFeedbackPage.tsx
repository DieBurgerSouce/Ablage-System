/**
 * OCRFeedbackPage
 *
 * Hauptseite fuer das OCR Feedback System mit Gamification.
 * Zeigt Leaderboard, Benutzer-Statistiken, Korrektur-Queue und Achievements.
 */

import { Award, Trophy, Target, Flame, HelpCircle } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { LeaderboardTable } from './components/LeaderboardTable';
import { UserStatsCard } from './components/UserStatsCard';
import { CorrectionQueue } from './components/CorrectionQueue';
import { useUserStats, useAchievements } from './hooks/use-ocr-feedback';

// Punkte-Konfiguration (entspricht Backend)
const POINTS_CONFIG = {
  text: { label: 'Text-Korrektur', points: 10 },
  amount: { label: 'Betrag-Korrektur', points: 15 },
  date: { label: 'Datum-Korrektur', points: 12 },
  entity: { label: 'Firma/Person', points: 20 },
  iban: { label: 'IBAN-Korrektur', points: 25 },
  vat_id: { label: 'USt-ID-Korrektur', points: 25 },
  reference: { label: 'Referenz-Korrektur', points: 15 },
};

const BONUS_TYPES = [
  { label: 'Grosse Korrektur', points: '+5' },
  { label: 'Niedrige Konfidenz (<60%)', points: '+10' },
  { label: 'Erste Korrektur des Tages', points: '+5' },
  { label: 'Streak-Bonus', points: '+3 pro Tag' },
  { label: 'Korrektur-Combo', points: '+2 pro Korrektur (max +20)' },
];

function PointsGuideCard() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <HelpCircle className="w-5 h-5" />
          Punkte-System
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div>
          <h4 className="font-medium mb-2">Basis-Punkte</h4>
          <div className="space-y-1">
            {Object.entries(POINTS_CONFIG).map(([key, { label, points }]) => (
              <div key={key} className="flex justify-between">
                <span className="text-muted-foreground">{label}</span>
                <Badge variant="secondary">{points} Pkt.</Badge>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h4 className="font-medium mb-2">Bonus-Punkte</h4>
          <div className="space-y-1">
            {BONUS_TYPES.map(({ label, points }) => (
              <div key={label} className="flex justify-between">
                <span className="text-muted-foreground">{label}</span>
                <Badge variant="outline">{points}</Badge>
              </div>
            ))}
          </div>
        </div>
        <div className="pt-2 text-xs text-muted-foreground">
          Mindestens 5 Korrekturen fuer Leaderboard-Platzierung erforderlich.
        </div>
      </CardContent>
    </Card>
  );
}

function AchievementsCard() {
  const { data: achievements, isLoading } = useAchievements();

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Award className="w-5 h-5" />
            Achievements
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-2">
            {[...Array(10)].map((_, i) => (
              <Skeleton key={i} className="h-10 w-10 rounded-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!achievements) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Award className="w-5 h-5" />
            Achievements
          </CardTitle>
          <Badge variant="secondary">
            {achievements.unlocked_count}/{achievements.total_achievements}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <TooltipProvider>
          <div className="grid grid-cols-5 gap-2">
            {achievements.achievements.map((ach) => (
              <Tooltip key={ach.id}>
                <TooltipTrigger asChild>
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center cursor-help transition-all ${
                      ach.unlocked
                        ? 'bg-primary/10 border border-primary/30'
                        : 'bg-muted/50 opacity-40'
                    }`}
                  >
                    <IconForAchievement icon={ach.icon} unlocked={ach.unlocked} />
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <div className="font-medium">{ach.name}</div>
                  <div className="text-xs text-muted-foreground">{ach.description}</div>
                  {!ach.unlocked && (
                    <div className="text-xs text-yellow-500 mt-1">Noch nicht freigeschaltet</div>
                  )}
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </TooltipProvider>
      </CardContent>
    </Card>
  );
}

function IconForAchievement({ icon, unlocked }: { icon: string; unlocked: boolean }) {
  const iconClass = `w-5 h-5 ${unlocked ? 'text-primary' : 'text-muted-foreground'}`;

  switch (icon) {
    case 'star':
      return <Award className={iconClass} />;
    case 'edit':
    case 'target':
      return <Target className={iconClass} />;
    case 'award':
    case 'trophy':
      return <Trophy className={iconClass} />;
    case 'flame':
    case 'fire':
      return <Flame className={iconClass} />;
    case 'crown':
    case 'diamond':
    case 'zap':
    default:
      return <Award className={iconClass} />;
  }
}

export function OCRFeedbackPage() {
  const { data: userStats, refetch: refetchStats } = useUserStats();

  const handleCorrectionComplete = () => {
    refetchStats();
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-3 rounded-lg bg-primary/10">
          <Trophy className="w-8 h-8 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">OCR Feedback Leaderboard</h1>
          <p className="text-muted-foreground">
            Korrigieren Sie OCR-Fehler und sammeln Sie Punkte fuer das Leaderboard.
          </p>
        </div>
      </div>

      {/* Benutzer-Info Alert wenn kein Rang */}
      {userStats && !userStats.weekly_rank && userStats.total_corrections < 5 && (
        <Alert>
          <Target className="h-4 w-4" />
          <AlertTitle>Noch {5 - userStats.total_corrections} Korrekturen bis zum Ranking</AlertTitle>
          <AlertDescription>
            Reichen Sie mindestens 5 Korrekturen ein, um im Leaderboard zu erscheinen.
            Korrigieren Sie Felder in der Queue unten, um Punkte zu sammeln.
          </AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <Trophy className="w-4 h-4" />
            Uebersicht
          </TabsTrigger>
          <TabsTrigger value="queue" className="flex items-center gap-2">
            <Target className="w-4 h-4" />
            Korrektur-Queue
          </TabsTrigger>
          <TabsTrigger value="achievements" className="flex items-center gap-2">
            <Award className="w-4 h-4" />
            Achievements
          </TabsTrigger>
        </TabsList>

        {/* Uebersicht Tab */}
        <TabsContent value="overview" className="space-y-6">
          {/* Eigene Stats */}
          <UserStatsCard />

          {/* Leaderboard */}
          <LeaderboardTable />
        </TabsContent>

        {/* Queue Tab */}
        <TabsContent value="queue" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <CorrectionQueue onCorrectionComplete={handleCorrectionComplete} />
            </div>
            <div>
              <PointsGuideCard />
            </div>
          </div>
        </TabsContent>

        {/* Achievements Tab */}
        <TabsContent value="achievements" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <AchievementsCard />
            <PointsGuideCard />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
