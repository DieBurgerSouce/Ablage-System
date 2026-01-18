/**
 * Smart Escalation Panel Komponente
 *
 * KI-gestuetzte intelligente Aufgabenzuweisung:
 * - Zuweisungsempfehlungen mit Score-Breakdown
 * - Team-Auslastungsuebersicht
 * - User-Score Debugging
 * - Faktor-Gewichtungen visualisieren
 *
 * Phase 2.3 der Feature-Roadmap (Januar 2026)
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Slider } from '@/components/ui/slider';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  useTeamWorkload,
  useEscalationFactors,
  useAssignmentRecommendation,
  type AssignmentRequest,
  type CandidateScore,
  type TeamMemberWorkload,
  type FactorWeights,
} from '../hooks/use-smart-escalation';
import {
  Users,
  User,
  Brain,
  Target,
  Clock,
  Calendar,
  Briefcase,
  UserCheck,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Info,
  Award,
  Activity,
  Settings,
  ChevronRight,
  Sparkles,
  Crown,
  BarChart3,
} from 'lucide-react';

// ==================== Utility Functions ====================

function formatPercent(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value / 100);
}

function getInitials(name: string): string {
  const parts = name.split(' ');
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600 dark:text-green-400';
  if (score >= 60) return 'text-lime-600 dark:text-lime-400';
  if (score >= 40) return 'text-yellow-600 dark:text-yellow-400';
  if (score >= 20) return 'text-orange-600 dark:text-orange-400';
  return 'text-red-600 dark:text-red-400';
}

function getScoreBarColor(score: number): string {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-lime-500';
  if (score >= 40) return 'bg-yellow-500';
  if (score >= 20) return 'bg-orange-500';
  return 'bg-red-500';
}

function getWorkloadStatus(score: number): { label: string; color: string; icon: typeof Activity } {
  if (score >= 80) {
    return { label: 'Gering', color: 'text-green-600', icon: TrendingDown };
  }
  if (score >= 50) {
    return { label: 'Moderat', color: 'text-yellow-600', icon: Activity };
  }
  return { label: 'Hoch', color: 'text-red-600', icon: TrendingUp };
}

// ==================== Factor Icons ====================

const FACTOR_ICONS: Record<string, typeof Brain> = {
  expertise: Brain,
  workload: Briefcase,
  availability: Calendar,
  relationship: UserCheck,
};

const FACTOR_LABELS: Record<string, string> = {
  expertise: 'Expertise',
  workload: 'Auslastung',
  availability: 'Verfuegbarkeit',
  relationship: 'Kundenbeziehung',
};

const FACTOR_DESCRIPTIONS: Record<string, string> = {
  expertise: 'Erfahrung mit diesem Dokumenttyp',
  workload: 'Aktuelle Arbeitsbelastung (invers)',
  availability: 'Verfuegbarkeit basierend auf Aktivitaet',
  relationship: 'Vorherige Zusammenarbeit mit dem Kunden',
};

// ==================== Score Bar Component ====================

function ScoreBar({ score, label, icon: Icon }: { score: number; label: string; icon?: typeof Brain }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground flex items-center gap-1">
          {Icon && <Icon className="h-3 w-3" />}
          {label}
        </span>
        <span className={getScoreColor(score)}>{score.toFixed(0)}</span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full ${getScoreBarColor(score)} rounded-full transition-all`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

// ==================== Candidate Card Component ====================

interface CandidateCardProps {
  candidate: CandidateScore;
  rank: number;
  isRecommended?: boolean;
  showDetails?: boolean;
}

function CandidateCard({ candidate, rank, isRecommended, showDetails = false }: CandidateCardProps) {
  const [expanded, setExpanded] = useState(showDetails);

  return (
    <Card className={`${isRecommended ? 'border-primary border-2' : ''}`}>
      <CardContent className="pt-4">
        <div className="flex items-start gap-3">
          {/* Rank Badge */}
          <div className="relative">
            <Avatar className="h-12 w-12">
              <AvatarFallback className={isRecommended ? 'bg-primary text-primary-foreground' : ''}>
                {getInitials(candidate.userName)}
              </AvatarFallback>
            </Avatar>
            {isRecommended && (
              <div className="absolute -top-1 -right-1">
                <Crown className="h-5 w-5 text-yellow-500 fill-yellow-500" />
              </div>
            )}
            <div className="absolute -bottom-1 -right-1 h-5 w-5 rounded-full bg-muted flex items-center justify-center text-xs font-bold">
              {rank}
            </div>
          </div>

          {/* User Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="font-medium truncate">{candidate.userName}</h4>
              {isRecommended && (
                <Badge variant="default" className="text-xs">
                  <Award className="h-3 w-3 mr-1" />
                  Empfohlen
                </Badge>
              )}
              {!candidate.isAvailable && (
                <Badge variant="secondary" className="text-xs">
                  Nicht verfuegbar
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground truncate">{candidate.userEmail}</p>

            {/* Total Score */}
            <div className="mt-2 flex items-center gap-2">
              <div className={`text-2xl font-bold ${getScoreColor(candidate.totalScore)}`}>
                {candidate.totalScore.toFixed(0)}
              </div>
              <span className="text-xs text-muted-foreground">/ 100 Punkte</span>
            </div>

            {/* Score Bars */}
            <div className="mt-3 space-y-2">
              <ScoreBar
                score={candidate.expertiseScore}
                label={FACTOR_LABELS.expertise}
                icon={FACTOR_ICONS.expertise}
              />
              <ScoreBar
                score={candidate.workloadScore}
                label={FACTOR_LABELS.workload}
                icon={FACTOR_ICONS.workload}
              />
              <ScoreBar
                score={candidate.availabilityScore}
                label={FACTOR_LABELS.availability}
                icon={FACTOR_ICONS.availability}
              />
              <ScoreBar
                score={candidate.relationshipScore}
                label={FACTOR_LABELS.relationship}
                icon={FACTOR_ICONS.relationship}
              />
            </div>

            {/* Unavailability Reason */}
            {!candidate.isAvailable && candidate.unavailabilityReason && (
              <Alert className="mt-3" variant="default">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle className="text-xs">Nicht verfuegbar</AlertTitle>
                <AlertDescription className="text-xs">
                  {candidate.unavailabilityReason}
                </AlertDescription>
              </Alert>
            )}

            {/* Expand Button */}
            {(Object.keys(candidate.expertiseDetails).length > 0 ||
              Object.keys(candidate.workloadDetails).length > 0) && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-2 h-6 text-xs"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? 'Weniger Details' : 'Mehr Details'}
                <ChevronRight className={`h-3 w-3 ml-1 transition-transform ${expanded ? 'rotate-90' : ''}`} />
              </Button>
            )}

            {/* Expanded Details */}
            {expanded && (
              <div className="mt-3 space-y-3 text-xs">
                {Object.keys(candidate.expertiseDetails).length > 0 && (
                  <div>
                    <p className="font-medium mb-1">Expertise-Details:</p>
                    <pre className="bg-muted p-2 rounded text-[10px] overflow-auto max-h-24">
                      {JSON.stringify(candidate.expertiseDetails, null, 2)}
                    </pre>
                  </div>
                )}
                {Object.keys(candidate.workloadDetails).length > 0 && (
                  <div>
                    <p className="font-medium mb-1">Auslastungs-Details:</p>
                    <pre className="bg-muted p-2 rounded text-[10px] overflow-auto max-h-24">
                      {JSON.stringify(candidate.workloadDetails, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Team Member Row Component ====================

function TeamMemberRow({ member }: { member: TeamMemberWorkload }) {
  const workloadStatus = getWorkloadStatus(member.workloadScore);
  const WorkloadIcon = workloadStatus.icon;

  return (
    <div className="flex items-center gap-3 py-3 border-b last:border-0">
      <Avatar className="h-10 w-10">
        <AvatarFallback>{getInitials(member.userName)}</AvatarFallback>
      </Avatar>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{member.userName}</span>
          {!member.isAvailable && (
            <Badge variant="secondary" className="text-xs">
              Abwesend
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-0.5">
          <span className="flex items-center gap-1">
            <Briefcase className="h-3 w-3" />
            {member.openItems} offen
          </span>
          <span className={`flex items-center gap-1 ${workloadStatus.color}`}>
            <WorkloadIcon className="h-3 w-3" />
            {workloadStatus.label}
          </span>
        </div>
      </div>

      <div className="text-right">
        <div className={`text-lg font-bold ${getScoreColor(member.workloadScore)}`}>
          {member.workloadScore.toFixed(0)}
        </div>
        <div className="text-xs text-muted-foreground">Verfuegbarkeit</div>
      </div>
    </div>
  );
}

// ==================== Factors Config Component ====================

interface FactorsConfigProps {
  weights: FactorWeights;
  onWeightsChange: (weights: FactorWeights) => void;
}

function FactorsConfig({ weights, onWeightsChange }: FactorsConfigProps) {
  const factors = ['expertise', 'workload', 'availability', 'relationship'] as const;

  const handleSliderChange = (factor: keyof FactorWeights, value: number[]) => {
    const newWeights = { ...weights, [factor]: value[0] / 100 };
    onWeightsChange(newWeights);
  };

  return (
    <div className="space-y-4">
      <div className="text-sm text-muted-foreground">
        Passen Sie die Gewichtung der einzelnen Faktoren an:
      </div>

      {factors.map((factor) => {
        const Icon = FACTOR_ICONS[factor];
        return (
          <div key={factor} className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">{FACTOR_LABELS[factor]}</span>
              </div>
              <span className="text-sm">{formatPercent(weights[factor] * 100)}</span>
            </div>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div>
                    <Slider
                      value={[weights[factor] * 100]}
                      onValueChange={(value) => handleSliderChange(factor, value)}
                      min={0}
                      max={100}
                      step={5}
                      className="w-full"
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{FACTOR_DESCRIPTIONS[factor]}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        );
      })}

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription className="text-xs">
          Die Summe der Gewichtungen sollte idealerweise 100% ergeben.
          Aktuell: {formatPercent((weights.expertise + weights.workload + weights.availability + weights.relationship) * 100)}
        </AlertDescription>
      </Alert>
    </div>
  );
}

// ==================== Recommendation Panel Component ====================

interface RecommendationPanelProps {
  request: AssignmentRequest;
  customWeights?: Partial<FactorWeights>;
}

function RecommendationPanel({ request, customWeights }: RecommendationPanelProps) {
  const { data, isLoading, error, refetch } = useAssignmentRecommendation(
    { ...request, weights: customWeights },
    true
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-48" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Fehler</AlertTitle>
        <AlertDescription>
          Die Empfehlung konnte nicht geladen werden.
          <Button variant="outline" size="sm" className="ml-2" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-1" />
            Erneut versuchen
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (!data || data.candidates.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Users className="h-12 w-12 mx-auto mb-4" />
        <p className="text-lg font-medium">Keine Kandidaten gefunden</p>
        <p className="text-sm">Es wurden keine passenden Bearbeiter gefunden.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Recommendation Summary */}
      <Card className="bg-gradient-to-br from-primary/5 to-primary/10 border-primary/20">
        <CardContent className="pt-4">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-full bg-primary/20 flex items-center justify-center">
              <Sparkles className="h-8 w-8 text-primary" />
            </div>
            <div className="flex-1">
              <div className="text-sm text-muted-foreground">KI-Empfehlung</div>
              <div className="text-xl font-bold">{data.recommendedUserName}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm text-muted-foreground">Confidence:</span>
                <Badge variant={data.confidence >= 80 ? 'default' : 'secondary'}>
                  {formatPercent(data.confidence)}
                </Badge>
              </div>
            </div>
            <div className="text-right">
              <p className="text-sm text-muted-foreground">{data.explanation}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Factors Used */}
      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-muted-foreground">Verwendete Faktoren:</span>
        {data.factorsUsed.map((factor) => {
          const Icon = FACTOR_ICONS[factor];
          return (
            <Badge key={factor} variant="outline" className="gap-1">
              <Icon className="h-3 w-3" />
              {FACTOR_LABELS[factor]} ({formatPercent(data.weightsUsed[factor as keyof FactorWeights] * 100)})
            </Badge>
          );
        })}
      </div>

      {/* Candidates List */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-muted-foreground">
          Kandidaten ({data.candidates.length})
        </h3>
        {data.candidates.map((candidate, index) => (
          <CandidateCard
            key={candidate.userId}
            candidate={candidate}
            rank={index + 1}
            isRecommended={candidate.userId === data.recommendedUserId}
            showDetails={candidate.userId === data.recommendedUserId}
          />
        ))}
      </div>
    </div>
  );
}

// ==================== Team Workload Panel Component ====================

function TeamWorkloadPanel() {
  const { data, isLoading, error, refetch } = useTeamWorkload();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Fehler</AlertTitle>
        <AlertDescription>
          Die Team-Auslastung konnte nicht geladen werden.
          <Button variant="outline" size="sm" className="ml-2" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-1" />
            Erneut versuchen
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (!data || data.teamMembers.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Users className="h-12 w-12 mx-auto mb-4" />
        <p className="text-lg font-medium">Kein Team gefunden</p>
        <p className="text-sm">Es wurden keine Team-Mitglieder gefunden.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Team-Mitglieder</p>
                <p className="text-2xl font-bold">{data.totalMembers}</p>
              </div>
              <Users className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Verfuegbar</p>
                <p className="text-2xl font-bold text-green-600">{data.availableMembers}</p>
              </div>
              <CheckCircle2 className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Offene Items</p>
                <p className="text-2xl font-bold">{data.totalOpenItems}</p>
              </div>
              <Briefcase className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Pro Mitarbeiter</p>
                <p className="text-2xl font-bold">{data.avgItemsPerMember.toFixed(1)}</p>
              </div>
              <BarChart3 className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Team Members List */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Team-Mitglieder</CardTitle>
          <CardDescription>
            Sortiert nach Verfuegbarkeit
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div>
            {[...data.teamMembers]
              .sort((a, b) => b.workloadScore - a.workloadScore)
              .map((member) => (
                <TeamMemberRow key={member.userId} member={member} />
              ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ==================== Main Panel Component ====================

export interface SmartEscalationPanelProps {
  /** Optional: Dokument-ID fuer Kontext */
  documentId?: string;
  /** Optional: Dokumenttyp fuer Expertise-Matching */
  documentType?: string;
  /** Optional: Entity-ID fuer Relationship-Matching */
  entityId?: string;
  /** Optional: Aufgabentyp */
  taskType?: string;
  /** Kompakte Darstellung */
  compact?: boolean;
}

export function SmartEscalationPanel({
  documentId,
  documentType,
  entityId,
  taskType,
  compact = false,
}: SmartEscalationPanelProps) {
  const [activeTab, setActiveTab] = useState('recommendation');
  const [customWeights, setCustomWeights] = useState<FactorWeights>({
    expertise: 0.35,
    workload: 0.25,
    availability: 0.25,
    relationship: 0.15,
  });

  const { data: factors } = useEscalationFactors();

  // Request for recommendation
  const request: AssignmentRequest = useMemo(
    () => ({
      documentId,
      documentType,
      entityId,
      taskType,
      maxCandidates: 10,
    }),
    [documentId, documentType, entityId, taskType]
  );

  // Compact mode - just show recommendation
  if (compact) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-purple-500" />
            <CardTitle className="text-base">Intelligente Zuweisung</CardTitle>
          </div>
          <CardDescription>
            KI-Empfehlung fuer optimale Bearbeiterzuweisung
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RecommendationPanel request={request} customWeights={customWeights} />
        </CardContent>
      </Card>
    );
  }

  // Full panel mode with tabs
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-purple-500" />
          Intelligente Aufgabenzuweisung
        </h2>
        <p className="text-muted-foreground">
          KI-gestuetzte Empfehlungen basierend auf Expertise, Auslastung und Verfuegbarkeit
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="recommendation" className="gap-1">
            <Award className="h-4 w-4" />
            Empfehlung
          </TabsTrigger>
          <TabsTrigger value="team" className="gap-1">
            <Users className="h-4 w-4" />
            Team
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-1">
            <Settings className="h-4 w-4" />
            Gewichtung
          </TabsTrigger>
        </TabsList>

        {/* Recommendation Tab */}
        <TabsContent value="recommendation" className="mt-4">
          <RecommendationPanel request={request} customWeights={customWeights} />
        </TabsContent>

        {/* Team Tab */}
        <TabsContent value="team" className="mt-4">
          <TeamWorkloadPanel />
        </TabsContent>

        {/* Settings Tab */}
        <TabsContent value="settings" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Faktor-Gewichtung</CardTitle>
              <CardDescription>
                Passen Sie an, wie stark die einzelnen Faktoren die Empfehlung beeinflussen
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FactorsConfig weights={customWeights} onWeightsChange={setCustomWeights} />

              {factors && (
                <div className="mt-6 pt-6 border-t">
                  <h4 className="text-sm font-medium mb-3">Schwellenwerte</h4>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div>
                      <span className="text-muted-foreground">Min. Expertise-Aufgaben:</span>
                      <span className="ml-2 font-medium">{factors.thresholds.minExpertiseTasks}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Max. Auslastungs-Items:</span>
                      <span className="ml-2 font-medium">{factors.thresholds.maxWorkloadItems}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Expertise-Zeitraum:</span>
                      <span className="ml-2 font-medium">{factors.thresholds.expertisePeriodDays} Tage</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Beziehungs-Zeitraum:</span>
                      <span className="ml-2 font-medium">{factors.thresholds.relationshipPeriodDays} Tage</span>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
