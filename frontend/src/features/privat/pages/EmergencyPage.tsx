/**
 * EmergencyPage - Notfallzugriff-Verwaltung
 *
 * Vertrauenspersonen und Notfallzugriff-Anfragen
 */

import * as React from 'react';
import { useParams } from '@tanstack/react-router';
import { EmergencyAccessPanel } from '../components/emergency/EmergencyAccessPanel';
import * as privatApi from '../api/privat-api';
import type {
  PrivatEmergencyContact,
  PrivatEmergencyAccessRequest,
} from '@/types/privat';
import { toast } from 'sonner';

export function EmergencyPage() {
  const { spaceId } = useParams({ strict: false }) as { spaceId?: string };

  const [contacts, setContacts] = React.useState<PrivatEmergencyContact[]>([]);
  const [requests, setRequests] = React.useState<PrivatEmergencyAccessRequest[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<Error | null>(null);

  // Load data
  React.useEffect(() => {
    const loadData = async () => {
      if (!spaceId) {
        setError(new Error('Kein Bereich ausgewählt'));
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
  }, [spaceId]);

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
    // TODO: Implement edit dialog
    toast.info('Bearbeiten wird implementiert');
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
