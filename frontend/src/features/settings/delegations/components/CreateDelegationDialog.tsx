/**
 * CreateDelegationDialog Component
 *
 * Dialog for creating a new delegation
 */

import { useState, useEffect } from 'react';
import { Plus, Search, User, Calendar, AlertCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { useUserSearch, useDelegationTemplates } from '../hooks';
import {
  DelegationType,
  DelegationReason,
  DELEGATION_TYPE_LABELS,
  DELEGATION_TYPE_DESCRIPTIONS,
  DELEGATION_REASON_LABELS,
} from '../types';
import type { DelegationCreateRequest, DelegationTemplate } from '../types';

interface CreateDelegationDialogProps {
  onSubmit: (request: DelegationCreateRequest) => void;
  isLoading?: boolean;
}

export function CreateDelegationDialog({
  onSubmit,
  isLoading = false,
}: CreateDelegationDialogProps) {
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [selectedUserName, setSelectedUserName] = useState<string>('');

  // Form state
  const [delegationType, setDelegationType] = useState<DelegationType>(
    DelegationType.APPROVAL
  );
  const [reason, setReason] = useState<DelegationReason>(DelegationReason.VACATION);
  const [reasonDetails, setReasonDetails] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [notifyOnAction, setNotifyOnAction] = useState(true);
  const [autoExtend, setAutoExtend] = useState(false);
  const [maxExtensions, setMaxExtensions] = useState(1);

  // Queries
  const { data: searchResults, isLoading: isSearching } = useUserSearch(
    searchQuery,
    open
  );
  const { data: templatesData } = useDelegationTemplates();

  // Set default dates
  useEffect(() => {
    if (open && !startDate) {
      const today = new Date();
      const defaultEnd = new Date();
      defaultEnd.setDate(today.getDate() + 14);

      setStartDate(today.toISOString().split('T')[0]);
      setEndDate(defaultEnd.toISOString().split('T')[0]);
    }
  }, [open, startDate]);

  const handleSelectUser = (user: { id: string; email: string; display_name?: string }) => {
    setSelectedUserId(user.id);
    setSelectedUserName(user.display_name || user.email);
    setSearchQuery('');
  };

  const handleSelectTemplate = (template: DelegationTemplate) => {
    setDelegationType(template.delegation_type);
    setNotifyOnAction(template.notify_on_action);
    setAutoExtend(template.auto_extend);
    setMaxExtensions(template.max_extensions);

    // Set end date based on template duration
    const end = new Date();
    end.setDate(end.getDate() + template.default_duration_days);
    setEndDate(end.toISOString().split('T')[0]);
  };

  const handleSubmit = () => {
    if (!selectedUserId || !startDate || !endDate) return;

    const request: DelegationCreateRequest = {
      delegate_id: selectedUserId,
      delegation_type: delegationType,
      reason,
      reason_details: reasonDetails || undefined,
      start_date: startDate,
      end_date: endDate,
      notify_on_action: notifyOnAction,
      auto_extend: autoExtend,
      max_extensions: autoExtend ? maxExtensions : 0,
    };

    onSubmit(request);
    setOpen(false);
    resetForm();
  };

  const resetForm = () => {
    setSelectedUserId(null);
    setSelectedUserName('');
    setSearchQuery('');
    setDelegationType(DelegationType.APPROVAL);
    setReason(DelegationReason.VACATION);
    setReasonDetails('');
    setStartDate('');
    setEndDate('');
    setNotifyOnAction(true);
    setAutoExtend(false);
    setMaxExtensions(1);
  };

  const isValid = selectedUserId && startDate && endDate && new Date(endDate) > new Date(startDate);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Neue Vertretung
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Vertretung einrichten</DialogTitle>
          <DialogDescription>
            Wählen Sie einen Vertreter und definieren Sie den Zeitraum und Umfang
            der Vertretung.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Templates */}
          {templatesData && templatesData.templates.length > 0 && (
            <div>
              <Label>Vorlage verwenden (optional)</Label>
              <Select onValueChange={(id) => {
                const template = templatesData.templates.find(t => t.id === id);
                if (template) handleSelectTemplate(template);
              }}>
                <SelectTrigger className="mt-1.5">
                  <SelectValue placeholder="Vorlage auswählen..." />
                </SelectTrigger>
                <SelectContent>
                  {templatesData.templates.map((template) => (
                    <SelectItem key={template.id} value={template.id}>
                      {template.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* User Search */}
          <div>
            <Label>Vertreter auswählen *</Label>
            {selectedUserId ? (
              <div className="mt-1.5 flex items-center justify-between p-3 border rounded-lg bg-muted/50">
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4" />
                  <span>{selectedUserName}</span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSelectedUserId(null);
                    setSelectedUserName('');
                  }}
                >
                  Ändern
                </Button>
              </div>
            ) : (
              <div className="mt-1.5 space-y-2">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Nach Name oder E-Mail suchen..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>
                {isSearching && (
                  <div className="space-y-2">
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                )}
                {searchResults && searchResults.users.length > 0 && (
                  <div className="border rounded-lg divide-y max-h-40 overflow-y-auto">
                    {searchResults.users.map((user) => (
                      <button
                        key={user.id}
                        type="button"
                        className="w-full px-3 py-2 text-left hover:bg-muted transition-colors flex items-center gap-2"
                        onClick={() => handleSelectUser(user)}
                      >
                        <User className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <div className="font-medium">
                            {user.display_name || user.email}
                          </div>
                          {user.display_name && (
                            <div className="text-xs text-muted-foreground">
                              {user.email}
                            </div>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
                {searchQuery.length >= 2 &&
                  !isSearching &&
                  searchResults?.users.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-2">
                      Keine Benutzer gefunden
                    </p>
                  )}
              </div>
            )}
          </div>

          {/* Delegation Type */}
          <div>
            <Label>Art der Vertretung *</Label>
            <Select
              value={delegationType}
              onValueChange={(v) => setDelegationType(v as DelegationType)}
            >
              <SelectTrigger className="mt-1.5">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.values(DelegationType).map((type) => (
                  <SelectItem key={type} value={type}>
                    <div>
                      <div>{DELEGATION_TYPE_LABELS[type]}</div>
                      <div className="text-xs text-muted-foreground">
                        {DELEGATION_TYPE_DESCRIPTIONS[type]}
                      </div>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Reason */}
          <div>
            <Label>Grund *</Label>
            <Select
              value={reason}
              onValueChange={(v) => setReason(v as DelegationReason)}
            >
              <SelectTrigger className="mt-1.5">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.values(DelegationReason).map((r) => (
                  <SelectItem key={r} value={r}>
                    {DELEGATION_REASON_LABELS[r]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Reason Details */}
          <div>
            <Label>Anmerkung (optional)</Label>
            <Textarea
              className="mt-1.5"
              placeholder="Zusätzliche Informationen für den Vertreter..."
              value={reasonDetails}
              onChange={(e) => setReasonDetails(e.target.value)}
              rows={2}
            />
          </div>

          {/* Date Range */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Startdatum *</Label>
              <div className="relative mt-1.5">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
            <div>
              <Label>Enddatum *</Label>
              <div className="relative mt-1.5">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  min={startDate}
                  className="pl-9"
                />
              </div>
            </div>
          </div>

          {/* Options */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label>Benachrichtigungen</Label>
                <p className="text-xs text-muted-foreground">
                  Bei jeder Aktion des Vertreters informieren
                </p>
              </div>
              <Switch
                checked={notifyOnAction}
                onCheckedChange={setNotifyOnAction}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label>Auto-Verlängerung</Label>
                <p className="text-xs text-muted-foreground">
                  Automatisch verlängern wenn nicht widerrufen
                </p>
              </div>
              <Switch checked={autoExtend} onCheckedChange={setAutoExtend} />
            </div>

            {autoExtend && (
              <div>
                <Label>Maximale Verlängerungen</Label>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={maxExtensions}
                  onChange={(e) => setMaxExtensions(Number(e.target.value))}
                  className="mt-1.5 w-24"
                />
              </div>
            )}
          </div>

          {delegationType === DelegationType.EMERGENCY && (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                Notfall-Vertretungen werden sofort aktiv ohne Bestätigung durch den
                Vertreter.
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Abbrechen
          </Button>
          <Button onClick={handleSubmit} disabled={!isValid || isLoading}>
            {isLoading ? 'Wird erstellt...' : 'Vertretung erstellen'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
