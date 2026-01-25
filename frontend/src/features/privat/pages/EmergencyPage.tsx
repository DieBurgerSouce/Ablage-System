/**
 * EmergencyPage - Notfallzugriff-Verwaltung
 *
 * Vertrauenspersonen und Notfallzugriff-Anfragen
 */

import * as React from 'react';
import { useParams, useSearch } from '@tanstack/react-router';
import { EmergencyAccessPanel } from '../components/emergency/EmergencyAccessPanel';
import * as privatApi from '../api/privat-api';
import { useDefaultSpace } from '../hooks/use-privat-queries';
import type {
  PrivatEmergencyContact,
  PrivatEmergencyAccessRequest,
} from '@/types/privat';
import { toast } from 'sonner';

interface EmergencyPageProps {
  spaceId?: string;
}

export function EmergencyPage({ spaceId: propSpaceId }: EmergencyPageProps = {}) {
  const params = useParams({ strict: false }) as { spaceId?: string };
  const search = useSearch({ strict: false }) as { space?: string };
  const { defaultSpaceId, isLoading: isLoadingSpaces, hasSpaces } = useDefaultSpace();

  // Priorität: 1. Props, 2. URL-Params, 3. Query-Param (?space=), 4. Default-Space
  const spaceId = propSpaceId || params.spaceId || search.space || defaultSpaceId;

  const [contacts, setContacts] = React.useState<PrivatEmergencyContact[]>([]);
  const [requests, setRequests] = React.useState<PrivatEmergencyAccessRequest[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);

  // Load data
  React.useEffect(() => {
    const loadData = async () => {
      // Warte auf Spaces wenn noch keine spaceId vorhanden
      if (isLoadingSpaces && !spaceId) {
        return;
      }

      if (!spaceId) {
        if (!hasSpaces) {
          setError(new Error('Noch keine Bereiche vorhanden. Erstellen Sie zuerst einen persönlichen Bereich.'));
        } else {
          setError(new Error('Kein Bereich ausgewählt'));
        }
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const [contactsData, requestsData] = await Promise.all([
          privatApi.listEmergencyContacts(spaceId),
          privatApi.listEmergencyRequests(spaceId),
        ]);
        setContacts(contactsData);
        setRequests(requestsData);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Fehler beim Laden'));
      } finally {
        setIsLoading(false);
      }
    };
    loadData();
  }, [spaceId, isLoadingSpaces, hasSpaces]);

  const handleAddContact = async (
    contact: Omit<PrivatEmergencyContact, 'id' | 'spaceId' | 'createdAt' | 'updatedAt' | 'isActive'>
  ) => {
    if (!spaceId) return;

    try {
      const newContact = await privatApi.createEmergencyContact(spaceId, contact);
      setContacts((prev) => [...prev, newContact]);
      toast.success('Vertrauensperson hinzugefügt');
    } catch (err) {
      toast.error('Fehler beim Hinzufügen der Vertrauensperson');
    }
  };

  const handleEditContact = async (contact: PrivatEmergencyContact) => {
    try {
      const updatedContact = await privatApi.updateEmergencyContact(contact.id, {
        firstName: contact.firstName,
        lastName: contact.lastName,
        email: contact.email,
        phone: contact.phone,
        relationship: contact.relationship,
        waitingPeriodDays: contact.waitingPeriodDays,
        notes: contact.notes,
      });
      setContacts((prev) =>
        prev.map((c) => (c.id === contact.id ? updatedContact : c))
      );
      toast.success('Vertrauensperson aktualisiert');
    } catch (err) {
      toast.error('Fehler beim Aktualisieren der Vertrauensperson');
    }
  };

  const handleDeleteContact = async (contact: PrivatEmergencyContact) => {
    if (!spaceId) return;

    try {
      await privatApi.deleteEmergencyContact(contact.id);
      setContacts((prev) => prev.filter((c) => c.id !== contact.id));
      toast.success('Vertrauensperson entfernt');
    } catch (err) {
      toast.error('Fehler beim Entfernen der Vertrauensperson');
    }
  };

  const handleApproveRequest = async (request: PrivatEmergencyAccessRequest) => {
    if (!spaceId) return;

    try {
      await privatApi.approveEmergencyRequest(request.id);
      setRequests((prev) =>
        prev.map((r) =>
          r.id === request.id
            ? { ...r, status: 'approved' as const, approvedAt: new Date().toISOString() }
            : r
        )
      );
      toast.success('Zugriff genehmigt');
    } catch (err) {
      toast.error('Fehler beim Genehmigen des Zugriffs');
    }
  };

  const handleDenyRequest = async (request: PrivatEmergencyAccessRequest, reason: string) => {
    if (!spaceId) return;

    try {
      await privatApi.denyEmergencyRequest(request.id, reason);
      setRequests((prev) =>
        prev.map((r) =>
          r.id === request.id
            ? { ...r, status: 'denied' as const, deniedAt: new Date().toISOString(), deniedReason: reason }
            : r
        )
      );
      toast.success('Zugriff abgelehnt');
    } catch (err) {
      toast.error('Fehler beim Ablehnen des Zugriffs');
    }
  };

  return (
    <div className="p-8">
      <EmergencyAccessPanel
        contacts={contacts}
        requests={requests}
        isLoading={isLoading}
        error={error}
        onAddContact={handleAddContact}
        onEditContact={handleEditContact}
        onDeleteContact={handleDeleteContact}
        onApproveRequest={handleApproveRequest}
        onDenyRequest={handleDenyRequest}
      />
    </div>
  );
}

export default EmergencyPage;
