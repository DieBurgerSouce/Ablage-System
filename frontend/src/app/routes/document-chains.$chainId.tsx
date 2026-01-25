/**
 * Document Chain Detail Route - Einzelne Auftragskette
 *
 * Zeigt die Details einer Auftragskette mit Dokumentenfluss-Visualisierung,
 * Abweichungen und Verknuepfungsaktionen.
 */

import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { ChainDetailPage } from '@/features/document-chains/components/ChainDetailPage';

export const Route = createFileRoute('/document-chains/$chainId')({
  component: DocumentChainDetailRoute,
});

function DocumentChainDetailRoute() {
  const { chainId } = Route.useParams();
  const navigate = useNavigate();

  const handleBack = () => {
    navigate({ to: '/document-chains' });
  };

  const handleDocumentClick = (documentId: string) => {
    navigate({ to: '/documents/$documentId', params: { documentId } });
  };

  return (
    <div className="p-8">
      <ChainDetailPage
        chainId={chainId}
        onBack={handleBack}
        onDocumentClick={handleDocumentClick}
      />
    </div>
  );
}
