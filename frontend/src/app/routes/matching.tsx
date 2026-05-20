/**
 * 3-Way-Matching Route
 *
 * Erweiterte Matching-Ansicht mit drei Tabs:
 * - Uebersicht: Erweiterte Liste mit 3-Spalten-Betragsvergleich
 * - Abgleich: Detail-Ansicht mit visuellem Diff und Abweichungskarten
 * - Statistiken: Wiederverwendung von POMatchStats
 *
 * Search-Parameter steuern Tab-Auswahl und Match-Detail.
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { GitCompareArrows } from 'lucide-react';
import { ThreeWayMatchView } from '@/features/matching/components/ThreeWayMatchView';

interface MatchingSearch {
  tab?: string;
  matchId?: string;
}

export const Route = createFileRoute('/matching')({
  validateSearch: (search: Record<string, unknown>): MatchingSearch => ({
    tab: (search.tab as string) || undefined,
    matchId: (search.matchId as string) || undefined,
  }),
  component: ThreeWayMatchingPage,
});

function ThreeWayMatchingPage() {
  const navigate = useNavigate({ from: '/matching' });
  const { tab, matchId } = Route.useSearch();

  const activeTab = tab || '\u00fcbersicht';

  function handleTabChange(value: string) {
    navigate({
      search: {
        tab: value === '\u00fcbersicht' ? undefined : value,
        matchId,
      },
    });
  }

  function handleSelectMatch(selectedId: string) {
    navigate({
      search: {
        tab: 'abgleich',
        matchId: selectedId,
      },
    });
  }

  function handleBack() {
    navigate({
      search: {
        tab: undefined,
        matchId: undefined,
      },
    });
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <GitCompareArrows className="h-8 w-8 text-primary" />
          <h1 className="text-3xl font-bold tracking-tight font-display">
            3-Way-Matching
          </h1>
        </div>
        <p className="text-muted-foreground mt-2">
          Erweiterter Abgleich: Bestellung, Lieferschein und Rechnung mit
          visuellem Diff und Abweichungsanalyse.
        </p>
      </div>

      {/* Content */}
      <ThreeWayMatchView
        activeTab={activeTab}
        selectedMatchId={matchId}
        onTabChange={handleTabChange}
        onSelectMatch={handleSelectMatch}
        onBack={handleBack}
      />
    </div>
  );
}
