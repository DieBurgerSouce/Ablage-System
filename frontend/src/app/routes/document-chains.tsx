/**
 * Document Chains Route - Auftragsketten Übersicht
 *
 * Zeigt alle Auftragsketten (Angebot → Auftrag → Lieferschein → Rechnung)
 * mit Filter- und Suchmöglichkeiten.
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { ChainListPage } from '@/features/document-chains/components/ChainListPage';

export const Route = createFileRoute('/document-chains')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('document_chains'),
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
