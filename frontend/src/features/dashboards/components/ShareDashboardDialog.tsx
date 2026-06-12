/**
 * Share Dashboard Dialog
 *
 * Dialog zum Teilen von Dashboards mit anderen Benutzern
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Search, X, UserPlus, Eye, Edit } from 'lucide-react';
import {
  useShareInfo,
  useShareDashboard,
  useUnshareDashboard,
} from '../hooks/useDashboards';
import type { PermissionLevel } from '../types';
import { useToast } from '@/components/ui/use-toast';

interface ShareDashboardDialogProps {
  dashboardId: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ShareDashboardDialog({
  dashboardId,
  isOpen,
  onClose,
}: ShareDashboardDialogProps) {
  const { toast } = useToast();
  const [userEmail, setUserEmail] = useState('');
  const [permission, setPermission] = useState<PermissionLevel>('view');

  const { data: shareInfo = [], isLoading } = useShareInfo(dashboardId);
  const shareMutation = useShareDashboard(dashboardId);
  const unshareMutation = useUnshareDashboard(dashboardId);

  const handleShare = async () => {
    if (!userEmail.trim()) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie eine E-Mail-Adresse ein',
        variant: 'destructive',
      });
      return;
    }

    try {
      // In real implementation, you'd first resolve email to user_id
      // For now, we'll use a placeholder
      await shareMutation.mutateAsync({
        user_id: 'placeholder', // Replace with actual user_id lookup
        permission,
      });

      toast({
        title: 'Dashboard geteilt',
        description: `Dashboard wurde mit ${userEmail} geteilt`,
      });

      setUserEmail('');
      setPermission('view');
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Dashboard konnte nicht geteilt werden',
        variant: 'destructive',
      });
    }
  };

  const handleUnshare = async (userId: string) => {
    try {
      await unshareMutation.mutateAsync(userId);
      toast({
        title: 'Berechtigung entfernt',
        description: 'Der Benutzer hat keinen Zugriff mehr auf das Dashboard',
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Berechtigung konnte nicht entfernt werden',
        variant: 'destructive',
      });
    }
  };

  const getInitials = (email: string) => {
    return email
      .split('@')[0]
      .split('.')
      .map((part) => part[0])
      .join('')
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Dashboard teilen</DialogTitle>
          <DialogDescription>
            Teilen Sie dieses Dashboard mit anderen Benutzern
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Add User Form */}
          <div className="space-y-3">
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="E-Mail-Adresse eingeben"
                  value={userEmail}
                  onChange={(e) => setUserEmail(e.target.value)}
                  className="pl-9"
                  onKeyPress={(e) => {
                    if (e.key === 'Enter') {
                      handleShare();
                    }
                  }}
                />
              </div>
              <Select
                value={permission}
                onValueChange={(value) => setPermission(value as PermissionLevel)}
              >
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="view">
                    <div className="flex items-center gap-2">
                      <Eye className="h-4 w-4" />
                      Ansehen
                    </div>
                  </SelectItem>
                  <SelectItem value="edit">
                    <div className="flex items-center gap-2">
                      <Edit className="h-4 w-4" />
                      Bearbeiten
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={handleShare}
              disabled={!userEmail.trim() || shareMutation.isPending}
              className="w-full"
            >
              <UserPlus className="h-4 w-4 mr-2" />
              Benutzer hinzufügen
            </Button>
          </div>

          {/* Shared Users List */}
          <div className="border-t pt-4">
            <div className="text-sm font-medium mb-3">
              Geteilt mit ({shareInfo.length})
            </div>
            {isLoading ? (
              <div className="text-sm text-muted-foreground text-center py-4">
                Lädt...
              </div>
            ) : shareInfo.length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-4">
                Noch nicht geteilt
              </div>
            ) : (
              <div className="space-y-2">
                {shareInfo.map((share) => (
                  <div
                    key={share.user_id}
                    className="flex items-center justify-between p-2 rounded-lg border"
                  >
                    <div className="flex items-center gap-3">
                      <Avatar className="h-8 w-8">
                        <AvatarFallback className="text-xs">
                          {getInitials(share.user_email)}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <div className="text-sm font-medium">
                          {share.user_email}
                        </div>
                        {share.shared_at && (
                          <div className="text-xs text-muted-foreground">
                            Geteilt{' '}
                            {new Date(share.shared_at).toLocaleDateString(
                              'de-DE'
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={
                          share.permission === 'edit' ? 'default' : 'secondary'
                        }
                      >
                        {share.permission === 'edit' ? (
                          <>
                            <Edit className="h-3 w-3 mr-1" />
                            Bearbeiten
                          </>
                        ) : (
                          <>
                            <Eye className="h-3 w-3 mr-1" />
                            Ansehen
                          </>
                        )}
                      </Badge>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => handleUnshare(share.user_id)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
