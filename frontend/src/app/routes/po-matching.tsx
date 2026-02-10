/**
 * PO-Matching Route
 *
 * Hauptseite fuer 3-Way Purchase Order Matching.
 * Tabs: Uebersicht (POMatchList), Statistiken (POMatchStats)
 * Detail-Ansicht via Search-Parameter.
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { POMatchList } from '@/features/po-matching/components/POMatchList';
import { POMatchDetail } from '@/features/po-matching/components/POMatchDetail';
import { POMatchStats } from '@/features/po-matching/components/POMatchStats';
import { GitCompareArrows } from 'lucide-react';

interface POMatchingSearch {
  tab?: string;
  matchId?: string;
}

export const Route = createFileRoute('/po-matching')({
  validateSearch: (search: Record<string, unknown>): POMatchingSearch => ({
    tab: (search.tab as string) || undefined,
    matchId: (search.matchId as string) || undefined,
  }),
  component: POMatchingPage,
});

function POMatchingPage() {
  const navigate = useNavigate({ from: '/po-matching' });
  const { tab, matchId } = Route.useSearch();

  // Detail-Ansicht wenn matchId vorhanden
  if (tab === 'detail' && matchId) {
    return (
      <div className="p-8">
        <POMatchDetail
          matchId={matchId}
          onBack={() =>
            navigate({
              search: { tab: undefined, matchId: undefined },
            })
          }
        />
      </div>
    );
  }

  const activeTab = tab === 'statistiken' ? 'statistiken' : 'uebersicht';

  function handleTabChange(value: string) {
    navigate({
      search: {
        tab: value === 'uebersicht' ? undefined : value,
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
            PO-Matching
          </h1>
        </div>
        <p className="text-muted-foreground mt-2">
          3-Way Matching: Bestellung, Lieferschein und Rechnung abgleichen.
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="uebersicht">Uebersicht</TabsTrigger>
          <TabsTrigger value="statistiken">Statistiken</TabsTrigger>
        </TabsList>

        <TabsContent value="uebersicht" className="mt-6">
          <POMatchList />
        </TabsContent>

        <TabsContent value="statistiken" className="mt-6">
          <POMatchStats />
        </TabsContent>
      </Tabs>
    </div>
  );
}
