/**
 * Document Chains Route - Auftragsketten Uebersicht
 *
 * Zeigt alle Auftragsketten (Angebot → Auftrag → Lieferschein → Rechnung)
 * mit Filter- und Suchmoeglichkeiten.
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { ChainListPage } from '@/features/document-chains/components/ChainListPage';

export const Route = createFileRoute('/document-chains')({
  component: DocumentChainsRoute,
});

function DocumentChainsRoute() {
  const navigate = useNavigate();

  const handleChainClick = (chainId: string) => {
    navigate({ to: '/document-chains/$chainId', params: { chainId } });
  };

  return (
    <div className="p-8 space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Auftragsketten</h1>
          <p className="text-muted-foreground mt-2">
            Verfolgen Sie den Dokumentenfluss von Angebot bis Rechnung.
          </p>
        </div>
      </div>

      <ChainListPage onChainClick={handleChainClick} />
    </div>
  );
}
