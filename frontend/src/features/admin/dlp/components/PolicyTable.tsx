/**
 * DLP Policy Table
 *
 * Tabelle zur Anzeige aller DLP-Policies mit Aktionen.
 */

import { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';
import {
  MoreHorizontal,
  Pencil,
  Trash2,
  Shield,
  ShieldOff,
  ShieldAlert,
  ShieldCheck,
  Bell,
  Droplets,
  Eye,
} from 'lucide-react';
import type { DLPPolicy, DLPAction } from '../api/dlp-api';
import { useDeletePolicy, useTogglePolicyEnabled } from '../hooks/use-dlp';

interface PolicyTableProps {
  policies: DLPPolicy[];
  isLoading?: boolean;
  onEdit: (policy: DLPPolicy) => void;
}

const actionLabels: Record<DLPAction, { label: string; variant: 'default' | 'destructive' | 'secondary' | 'outline' }> = {
  allow: { label: 'Erlauben', variant: 'default' },
  block: { label: 'Blockieren', variant: 'destructive' },
  watermark: { label: 'Wasserzeichen', variant: 'secondary' },
  notify: { label: 'Benachrichtigen', variant: 'outline' },
  audit_only: { label: 'Nur Logging', variant: 'outline' },
};

const ActionIcon = ({ action }: { action: DLPAction }) => {
  const icons: Record<DLPAction, React.ReactNode> = {
    allow: <ShieldCheck className="h-4 w-4 text-green-500" />,
    block: <ShieldOff className="h-4 w-4 text-red-500" />,
    watermark: <Droplets className="h-4 w-4 text-blue-500" />,
    notify: <Bell className="h-4 w-4 text-yellow-500" />,
    audit_only: <Eye className="h-4 w-4 text-muted-foreground" />,
  };
  return icons[action];
};

export function PolicyTable({ policies, isLoading, onEdit }: PolicyTableProps) {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedPolicy, setSelectedPolicy] = useState<DLPPolicy | null>(null);

  const deleteMutation = useDeletePolicy();

  const handleDelete = (policy: DLPPolicy) => {
    setSelectedPolicy(policy);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = () => {
    if (selectedPolicy) {
      deleteMutation.mutate(selectedPolicy.id);
      setDeleteDialogOpen(false);
      setSelectedPolicy(null);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (policies.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <Shield className="h-12 w-12 text-muted-foreground mb-4" />
        <h3 className="text-lg font-medium">Keine Policies vorhanden</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Erstellen Sie eine neue DLP-Policy, um Dokumente zu schützen.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[50px]">Status</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Aktion</TableHead>
              <TableHead>Rollen</TableHead>
              <TableHead>Dokument-Typen</TableHead>
              <TableHead>Optionen</TableHead>
              <TableHead className="w-[70px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {policies.map((policy) => (
              <PolicyRow
                key={policy.id}
                policy={policy}
                onEdit={onEdit}
                onDelete={handleDelete}
              />
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Policy löschen?</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Policy "{selectedPolicy?.name}" wirklich löschen?
              Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

// ==================== Policy Row ====================

interface PolicyRowProps {
  policy: DLPPolicy;
  onEdit: (policy: DLPPolicy) => void;
  onDelete: (policy: DLPPolicy) => void;
}

function PolicyRow({ policy, onEdit, onDelete }: PolicyRowProps) {
  const toggleMutation = useTogglePolicyEnabled(policy.id);
  const actionInfo = actionLabels[policy.action];

  const handleToggle = (checked: boolean) => {
    toggleMutation.mutate(checked);
  };

  return (
    <TableRow>
      {/* Status Toggle */}
      <TableCell>
        <Switch
          checked={policy.enabled}
          onCheckedChange={handleToggle}
          disabled={toggleMutation.isPending}
          aria-label={policy.enabled ? 'Deaktivieren' : 'Aktivieren'}
        />
      </TableCell>

      {/* Name & Description */}
      <TableCell>
        <div className="flex items-center gap-2">
          <ActionIcon action={policy.action} />
          <div>
            <div className="font-medium">{policy.name}</div>
            {policy.description && (
              <div className="text-sm text-muted-foreground truncate max-w-[200px]">
                {policy.description}
              </div>
            )}
          </div>
        </div>
      </TableCell>

      {/* Action */}
      <TableCell>
        <Badge variant={actionInfo.variant}>{actionInfo.label}</Badge>
      </TableCell>

      {/* Roles */}
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {policy.allowed_roles.slice(0, 2).map((role) => (
            <Badge key={role} variant="outline" className="text-xs">
              {role}
            </Badge>
          ))}
          {policy.allowed_roles.length > 2 && (
            <Badge variant="outline" className="text-xs">
              +{policy.allowed_roles.length - 2}
            </Badge>
          )}
          {policy.blocked_roles.length > 0 && (
            <Badge variant="destructive" className="text-xs">
              -{policy.blocked_roles.length} blockiert
            </Badge>
          )}
        </div>
      </TableCell>

      {/* Document Types */}
      <TableCell>
        <div className="flex flex-wrap gap-1">
          {policy.document_types.slice(0, 2).map((type) => (
            <Badge key={type} variant="secondary" className="text-xs">
              {type === 'all' ? 'Alle' : type}
            </Badge>
          ))}
          {policy.document_types.length > 2 && (
            <Badge variant="secondary" className="text-xs">
              +{policy.document_types.length - 2}
            </Badge>
          )}
        </div>
      </TableCell>

      {/* Options */}
      <TableCell>
        <div className="flex items-center gap-2">
          {policy.require_watermark && (
            <span title="Wasserzeichen erforderlich">
              <Droplets className="h-4 w-4 text-blue-500" />
            </span>
          )}
          {policy.notify_admin && (
            <span title="Admin-Benachrichtigung">
              <Bell className="h-4 w-4 text-yellow-500" />
            </span>
          )}
          {policy.log_access && (
            <span title="Zugriffs-Logging">
              <Eye className="h-4 w-4 text-muted-foreground" />
            </span>
          )}
          {policy.time_restrictions && (
            <span title="Zeitbeschränkung">
              <ShieldAlert className="h-4 w-4 text-orange-500" />
            </span>
          )}
        </div>
      </TableCell>

      {/* Actions Menu */}
      <TableCell>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreHorizontal className="h-4 w-4" />
              <span className="sr-only">Aktionen</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit(policy)}>
              <Pencil className="h-4 w-4 mr-2" />
              Bearbeiten
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => onDelete(policy)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Löschen
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  );
}
