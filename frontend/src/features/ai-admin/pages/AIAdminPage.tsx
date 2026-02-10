/**
 * AI Admin Page
 *
 * Hauptseite fuer KI-Autonomie Verwaltung mit Tabs.
 */

import { Brain } from 'lucide-react';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';

import { AISettingsPanel } from '../components/AISettingsPanel';
import { AIStatsOverview } from '../components/AIStatsOverview';
import { FeedbackQueue } from '../components/FeedbackQueue';
import { usePendingReviewCount } from '../hooks/useAIAdmin';

// =============================================================================
// Main Component
// =============================================================================

export function AIAdminPage() {
  const { data: pendingCount } = usePendingReviewCount();

  const totalPending = pendingCount
    ? Object.values(pendingCount).reduce((sum, count) => sum + count, 0)
    : 0;

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Page Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <Brain className="h-8 w-8 text-primary" />
          <h1 className="text-3xl font-bold">KI-Autonomie Verwaltung</h1>
        </div>
        <p className="text-muted-foreground">
          Verwalten Sie KI-Entscheidungen, Schwellenwerte und Performance-Statistiken
        </p>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="settings" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 lg:w-[600px]">
          <TabsTrigger value="settings">Einstellungen</TabsTrigger>
          <TabsTrigger value="stats">Statistiken</TabsTrigger>
          <TabsTrigger value="queue" className="relative">
            Prüf-Warteschlange
            {totalPending > 0 && (
              <Badge
                variant="destructive"
                className="ml-2 h-5 w-5 flex items-center justify-center p-0 text-xs"
              >
                {totalPending > 99 ? '99+' : totalPending}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="settings" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>KI-Schwellenwerte</CardTitle>
              <CardDescription>
                Konfigurieren Sie die Konfidenz-Schwellenwerte für automatische
                Entscheidungen. Höhere Schwellenwerte bedeuten mehr manuelle Reviews,
                niedrigere Schwellenwerte mehr Automatisierung.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <AISettingsPanel />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="stats" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Performance-Statistiken</CardTitle>
              <CardDescription>
                Übersicht über KI-Genauigkeit, Automatisierungsraten und Lernfortschritt
              </CardDescription>
            </CardHeader>
            <CardContent>
              <AIStatsOverview />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="queue" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Entscheidungen prüfen</CardTitle>
              <CardDescription>
                Überprüfen Sie KI-Entscheidungen, die manuelle Bestätigung erfordern.
                Ihr Feedback hilft dem System zu lernen.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FeedbackQueue />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
