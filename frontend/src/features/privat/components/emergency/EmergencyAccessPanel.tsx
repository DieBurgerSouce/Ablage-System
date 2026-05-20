/**
 * EmergencyAccessPanel - Notfallzugriff-Verwaltung
 *
 * Verwaltet Vertrauenspersonen und Notfallzugriff-Anfragen
 */

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Plus,
  MoreHorizontal,
  UserPlus,
  Shield,
  Edit,
  Trash2,
  AlertTriangle,
  Clock,
  CheckCircle,
  XCircle,
  Phone,
  Mail,
  Calendar,
} from 'lucide-react';
import type {
  PrivatEmergencyContact,
  PrivatEmergencyAccessRequest,
  PrivatEmergencyAccessStatus,
} from '@/types/privat';
import { cn } from '@/lib/utils';

interface EmergencyAccessPanelProps {
  contacts: PrivatEmergencyContact[];
  requests: PrivatEmergencyAccessRequest[];
  isLoading?: boolean;
  error?: Error | null;
  onAddContact?: (contact: Omit<PrivatEmergencyContact, 'id' | 'spaceId' | 'createdAt' | 'updatedAt'>) => void;
  onEditContact?: (contact: PrivatEmergencyContact) => void;
  onDeleteContact?: (contact: PrivatEmergencyContact) => void;
  onApproveRequest?: (request: PrivatEmergencyAccessRequest) => void;
  onDenyRequest?: (request: PrivatEmergencyAccessRequest, reason: string) => void;
  className?: string;
}

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getStatusBadge = (status: PrivatEmergencyAccessStatus): React.ReactNode => {
  switch (status) {
    case 'pending':
      return (
        <Badge variant="secondary" className="bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
          <Clock className="h-3 w-3 mr-1" />
          Wartend
        </Badge>
      );
    case 'approved':
      return (
        <Badge variant="secondary" className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
          <CheckCircle className="h-3 w-3 mr-1" />
          Genehmigt
        </Badge>
      );
    case 'denied':
      return (
        <Badge variant="secondary" className="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
          <XCircle className="h-3 w-3 mr-1" />
          Abgelehnt
        </Badge>
      );
    case 'expired':
      return (
        <Badge variant="secondary" className="bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200">
          <Clock className="h-3 w-3 mr-1" />
          Abgelaufen
        </Badge>
      );
    default:
      return null;
  }
};

export function EmergencyAccessPanel({
  contacts,
  requests,
  isLoading,
  error,
  onAddContact,
  onEditContact,
  onDeleteContact,
  onApproveRequest,
  onDenyRequest,
  className,
}: EmergencyAccessPanelProps) {
  const [isAddDialogOpen, setIsAddDialogOpen] = React.useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = React.useState(false);
  const [selectedContact, setSelectedContact] = React.useState<PrivatEmergencyContact | null>(null);
  const [denyReason, setDenyReason] = React.useState('');
  const [selectedRequest, setSelectedRequest] = React.useState<PrivatEmergencyAccessRequest | null>(null);

  // Handler für Edit öffnen
  const handleOpenEditDialog = React.useCallback((contact: PrivatEmergencyContact) => {
    setSelectedContact(contact);
    setIsEditDialogOpen(true);
  }, []);

  const pendingRequests = requests.filter((r) => r.status === 'pending');

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>Notfallzugriff</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Notfallzugriff-Daten
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-950">
            <Shield className="h-6 w-6 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Notfallzugriff</h1>
            <p className="text-muted-foreground">
              Vertrauenspersonen und Zugriffs-Anfragen verwalten
            </p>
          </div>
        </div>
      </div>

      {/* Pending Requests Alert */}
      {pendingRequests.length > 0 && (
        <Card className="border-amber-500/50 bg-amber-50/50 dark:bg-amber-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center gap-2 text-amber-800 dark:text-amber-200">
              <AlertTriangle className="h-5 w-5" />
              {pendingRequests.length} offene{' '}
              {pendingRequests.length === 1 ? 'Anfrage' : 'Anfragen'}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {pendingRequests.map((request) => (
                <PendingRequestItem
                  key={request.id}
                  request={request}
                  contacts={contacts}
                  onApprove={onApproveRequest}
                  onDeny={(req) => {
                    setSelectedRequest(req);
                  }}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Trusted Contacts */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <UserPlus className="h-5 w-5 text-blue-500" />
                Vertrauenspersonen
              </CardTitle>
              <CardDescription>
                Personen, die im Notfall Zugriff anfordern können
              </CardDescription>
            </div>
            {onAddContact && (
              <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
                <DialogTrigger asChild>
                  <Button>
                    <Plus className="mr-2 h-4 w-4" />
                    Hinzufügen
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <AddContactForm
                    onSubmit={(contact) => {
                      onAddContact(contact);
                      setIsAddDialogOpen(false);
                    }}
                    onCancel={() => setIsAddDialogOpen(false)}
                  />
                </DialogContent>
              </Dialog>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2].map((i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
          ) : contacts.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <UserPlus className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="mb-2">Keine Vertrauenspersonen hinterlegt</p>
              <p className="text-sm">
                Fügen Sie Personen hinzu, die im Notfall Zugriff anfordern können.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {contacts.map((contact) => (
                <ContactCard
                  key={contact.id}
                  contact={contact}
                  onEdit={handleOpenEditDialog}
                  onDelete={onDeleteContact}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Request History */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-muted-foreground" />
            Anfrage-Verlauf
          </CardTitle>
          <CardDescription>
            Vergangene Notfallzugriff-Anfragen
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : requests.length === 0 ? (
            <p className="text-center py-4 text-muted-foreground">
              Keine Anfragen vorhanden
            </p>
          ) : (
            <div className="space-y-3">
              {requests.map((request) => {
                const contact = contacts.find((c) => c.id === request.contactId);
                return (
                  <div
                    key={request.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                  >
                    <div>
                      <p className="font-medium">
                        {contact
                          ? `${contact.firstName} ${contact.lastName}`
                          : 'Unbekannt'}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {formatDate(request.requestedAt)}
                        {request.reason && ` - ${request.reason}`}
                      </p>
                    </div>
                    {getStatusBadge(request.status)}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Deny Dialog */}
      <AlertDialog
        open={selectedRequest !== null}
        onOpenChange={(open) => !open && setSelectedRequest(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Anfrage ablehnen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie diese Notfallzugriff-Anfrage wirklich ablehnen?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-4">
            <Label htmlFor="denyReason">Grund (optional)</Label>
            <Input
              id="denyReason"
              value={denyReason}
              onChange={(e) => setDenyReason(e.target.value)}
              placeholder="Grund für die Ablehnung..."
              className="mt-2"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDenyReason('')}>
              Abbrechen
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (selectedRequest && onDenyRequest) {
                  onDenyRequest(selectedRequest, denyReason);
                  setSelectedRequest(null);
                  setDenyReason('');
                }
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Ablehnen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Edit Contact Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent>
          {selectedContact && (
            <EditContactForm
              contact={selectedContact}
              onSubmit={(updatedContact) => {
                onEditContact?.({ ...selectedContact, ...updatedContact });
                setIsEditDialogOpen(false);
                setSelectedContact(null);
              }}
              onCancel={() => {
                setIsEditDialogOpen(false);
                setSelectedContact(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface ContactCardProps {
  contact: PrivatEmergencyContact;
  onEdit?: (contact: PrivatEmergencyContact) => void;
  onDelete?: (contact: PrivatEmergencyContact) => void;
}

function ContactCard({ contact, onEdit, onDelete }: ContactCardProps) {
  return (
    <div className="flex items-center justify-between p-4 rounded-lg border">
      <div className="flex items-center gap-4">
        <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
          <span className="text-lg font-medium text-primary">
            {contact.firstName[0]}
            {contact.lastName[0]}
          </span>
        </div>
        <div>
          <h4 className="font-medium">
            {contact.firstName} {contact.lastName}
          </h4>
          {contact.relationship && (
            <p className="text-sm text-muted-foreground">{contact.relationship}</p>
          )}
          <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
            {contact.email && (
              <span className="flex items-center gap-1">
                <Mail className="h-3 w-3" />
                {contact.email}
              </span>
            )}
            {contact.phone && (
              <span className="flex items-center gap-1">
                <Phone className="h-3 w-3" />
                {contact.phone}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <Badge variant="outline">
            <Clock className="h-3 w-3 mr-1" />
            {contact.waitingPeriodDays} Tage Wartezeit
          </Badge>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit?.(contact)}>
              <Edit className="mr-2 h-4 w-4" />
              Bearbeiten
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => onDelete?.(contact)}
              className="text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Entfernen
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

interface PendingRequestItemProps {
  request: PrivatEmergencyAccessRequest;
  contacts: PrivatEmergencyContact[];
  onApprove?: (request: PrivatEmergencyAccessRequest) => void;
  onDeny?: (request: PrivatEmergencyAccessRequest) => void;
}

function PendingRequestItem({
  request,
  contacts,
  onApprove,
  onDeny,
}: PendingRequestItemProps) {
  const contact = contacts.find((c) => c.id === request.contactId);
  const waitingUntil = new Date(request.waitingUntil);
  const now = new Date();
  const isWaitingPeriodOver = waitingUntil <= now;

  return (
    <div className="flex items-center justify-between p-3 bg-white dark:bg-gray-900 rounded-lg">
      <div>
        <p className="font-medium">
          {contact ? `${contact.firstName} ${contact.lastName}` : 'Unbekannt'}
        </p>
        <p className="text-sm text-muted-foreground">
          Angefragt: {formatDate(request.requestedAt)}
        </p>
        {request.reason && (
          <p className="text-sm mt-1">Grund: {request.reason}</p>
        )}
        <p className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
          <Calendar className="h-3 w-3" />
          {isWaitingPeriodOver
            ? 'Wartezeit abgelaufen - Zugriff wird automatisch gewährt'
            : `Wartezeit bis: ${formatDate(request.waitingUntil)}`}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => onDeny?.(request)}
          className="text-destructive"
        >
          <XCircle className="h-4 w-4 mr-1" />
          Ablehnen
        </Button>
        <Button size="sm" onClick={() => onApprove?.(request)}>
          <CheckCircle className="h-4 w-4 mr-1" />
          Genehmigen
        </Button>
      </div>
    </div>
  );
}

interface AddContactFormProps {
  onSubmit: (contact: Omit<PrivatEmergencyContact, 'id' | 'spaceId' | 'createdAt' | 'updatedAt' | 'isActive'>) => void;
  onCancel: () => void;
}

function AddContactForm({ onSubmit, onCancel }: AddContactFormProps) {
  const [firstName, setFirstName] = React.useState('');
  const [lastName, setLastName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [phone, setPhone] = React.useState('');
  const [relationship, setRelationship] = React.useState('');
  const [waitingPeriodDays, setWaitingPeriodDays] = React.useState(30);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      firstName,
      lastName,
      email,
      phone: phone || undefined,
      relationship: relationship || undefined,
      waitingPeriodDays,
      notes: undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <DialogHeader>
        <DialogTitle>Vertrauensperson hinzufügen</DialogTitle>
        <DialogDescription>
          Diese Person kann im Notfall Zugriff auf Ihre Dokumente anfordern.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-4 py-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="firstName">Vorname *</Label>
            <Input
              id="firstName"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              required
            />
          </div>
          <div>
            <Label htmlFor="lastName">Nachname *</Label>
            <Input
              id="lastName"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              required
            />
          </div>
        </div>
        <div>
          <Label htmlFor="email">E-Mail *</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <Label htmlFor="phone">Telefon</Label>
          <Input
            id="phone"
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="relationship">Beziehung</Label>
          <Input
            id="relationship"
            value={relationship}
            onChange={(e) => setRelationship(e.target.value)}
            placeholder="z.B. Ehepartner, Kind, Anwalt..."
          />
        </div>
        <div>
          <Label htmlFor="waitingPeriod">Wartezeit (Tage) *</Label>
          <Input
            id="waitingPeriod"
            type="number"
            min={1}
            max={365}
            value={waitingPeriodDays}
            onChange={(e) => setWaitingPeriodDays(Number(e.target.value))}
          />
          <p className="text-sm text-muted-foreground mt-1">
            Zeitraum, in dem Sie eine Anfrage ablehnen können
          </p>
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit">Hinzufügen</Button>
      </DialogFooter>
    </form>
  );
}

interface EditContactFormProps {
  contact: PrivatEmergencyContact;
  onSubmit: (contact: Partial<Omit<PrivatEmergencyContact, 'id' | 'spaceId' | 'createdAt' | 'updatedAt'>>) => void;
  onCancel: () => void;
}

function EditContactForm({ contact, onSubmit, onCancel }: EditContactFormProps) {
  const [firstName, setFirstName] = React.useState(contact.firstName);
  const [lastName, setLastName] = React.useState(contact.lastName);
  const [email, setEmail] = React.useState(contact.email);
  const [phone, setPhone] = React.useState(contact.phone || '');
  const [relationship, setRelationship] = React.useState(contact.relationship || '');
  const [waitingPeriodDays, setWaitingPeriodDays] = React.useState(contact.waitingPeriodDays);
  const [notes, setNotes] = React.useState(contact.notes || '');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      firstName,
      lastName,
      email,
      phone: phone || undefined,
      relationship: relationship || undefined,
      waitingPeriodDays,
      notes: notes || undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <DialogHeader>
        <DialogTitle>Vertrauensperson bearbeiten</DialogTitle>
        <DialogDescription>
          Ändern Sie die Daten der Vertrauensperson.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-4 py-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="edit-firstName">Vorname *</Label>
            <Input
              id="edit-firstName"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              required
            />
          </div>
          <div>
            <Label htmlFor="edit-lastName">Nachname *</Label>
            <Input
              id="edit-lastName"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              required
            />
          </div>
        </div>
        <div>
          <Label htmlFor="edit-email">E-Mail *</Label>
          <Input
            id="edit-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <Label htmlFor="edit-phone">Telefon</Label>
          <Input
            id="edit-phone"
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="edit-relationship">Beziehung</Label>
          <Input
            id="edit-relationship"
            value={relationship}
            onChange={(e) => setRelationship(e.target.value)}
            placeholder="z.B. Ehepartner, Kind, Anwalt..."
          />
        </div>
        <div>
          <Label htmlFor="edit-waitingPeriod">Wartezeit (Tage) *</Label>
          <Input
            id="edit-waitingPeriod"
            type="number"
            min={1}
            max={365}
            value={waitingPeriodDays}
            onChange={(e) => setWaitingPeriodDays(Number(e.target.value))}
          />
          <p className="text-sm text-muted-foreground mt-1">
            Zeitraum, in dem Sie eine Anfrage ablehnen können
          </p>
        </div>
        <div>
          <Label htmlFor="edit-notes">Notizen</Label>
          <Input
            id="edit-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Zusätzliche Informationen..."
          />
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Abbrechen
        </Button>
        <Button type="submit">Speichern</Button>
      </DialogFooter>
    </form>
  );
}

export default EmergencyAccessPanel;
