/**
 * Zusammenfassende Meldung Route
 *
 * ZM summary page for EU intra-community reporting.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ZmSummaryCard } from '@/components/streckengeschaeft';

export const Route = createFileRoute('/streckengeschaeft/zm')({
  component: ZmPage,
});

function ZmPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          Zusammenfassende Meldung
        </h1>
        <p className="text-muted-foreground">
          Innergemeinschaftliche Lieferungen gemäß Paragraph 18a UStG
        </p>
      </div>
      <ZmSummaryCard />
    </div>
  );
}
