/**
 * ShareDialog Component
 * German Enterprise Document Platform
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Trash2, UserPlus, Share2 } from 'lucide-react';
import type { ShareInfo } from '../types/adhoc-reporting-types';
import { PERMISSION_LABELS } from '../types/adhoc-reporting-types';

interface ShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shares: ShareInfo[];
  onShare: (userIds: number[], permission: 'read' | 'write') => Promise<void>;
  onRemoveShare: (shareId: number) => Promise<void>;
  isLoading?: boolean;
}

export function ShareDialog({
  open,
  onOpenChange,
  shares,
  onShare,
  onRemoveShare,
  isLoading = false,
}: ShareDialogProps) {
  const [userIdInput, setUserIdInput] = useState('');
  const [permission, setPermission] = useState<'read' | 'write'>('read');
  const [isSharing, setIsSharing] = useState(false);

  const handleShare = async () => {
    const userId = parseInt(userIdInput, 10);
    if (isNaN(userId) || userId <= 0) {
      return;
    }

    setIsSharing(true);
    try {
      await onShare([userId], permission);
      setUserIdInput('');
      setPermission('read');
    } finally {
      setIsSharing(false);
    }
  };

  const handleRemoveShare = async (shareId: number) => {
    await onRemoveShare(shareId);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <Share2 className="h-5 w-5" />
            <span>Report freigeben</span>
          </DialogTitle>
          <DialogDescription>
            Geben Sie diesen Report für andere Benutzer frei
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Add Share */}
          <div className="space-y-3">
            <Label>Neue Freigabe hinzufügen</Label>
            <div className="flex space-x-2">
              <div className="flex-1">
                <Input
                  type="number"
                  placeholder="Benutzer-ID"
                  value={userIdInput}
                  onChange={(e) => setUserIdInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleShare();
                    }
                  }}
                />
              </div>
              <Select value={permission} onValueChange={(v) => setPermission(v as 'read' | 'write')}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="Berechtigung" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="read">Lesen</SelectItem>
                  <SelectItem value="write">Bearbeiten</SelectItem>
                </SelectContent>
              </Select>
              <Button
                onClick={handleShare}
                disabled={!userIdInput || isSharing}
              >
                <UserPlus className="h-4 w-4 mr-2" />
                Hinzufügen
              </Button>
            </div>
          </div>

          {/* Current Shares */}
          <div className="space-y-3">
            <Label>Aktuelle Freigaben</Label>
            {shares.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">
                Keine Freigaben vorhanden
              </div>
            ) : (
              <div className="border rounded-lg">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Benutzer</TableHead>
                      <TableHead>Berechtigung</TableHead>
                      <TableHead>Freigegeben am</TableHead>
                      <TableHead className="text-right">Aktionen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {shares.map((share) => (
                      <TableRow key={share.id}>
                        <TableCell>
                          <div>
                            <div className="font-medium">
                              {share.user_name || `Benutzer #${share.user_id}`}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              ID: {share.user_id}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={share.permission === 'write' ? 'default' : 'secondary'}>
                            {PERMISSION_LABELS[share.permission]}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {new Date(share.shared_at).toLocaleDateString('de-DE')}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleRemoveShare(share.id)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
