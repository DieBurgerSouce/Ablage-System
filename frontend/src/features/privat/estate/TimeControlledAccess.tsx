/**
 * TimeControlledAccess Component
 *
 * Verwaltet zeitgesteuerten Zugriff auf Dokumente für Erben.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Clock,
  Plus,
  Lock,
  Unlock,
  AlertTriangle,
  Users,
  Calendar,
  Key,
} from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

interface TimeControlledAccessProps {
  spaceId: string;
}

// Mock-Daten für Demonstration
const mockAccessRules = [
  {
    id: '1',
    beneficiaryName: 'Max Mustermann',
    accessType: 'death',
    triggerEvent: 'Nach meinem Tod',
    folders: ['Vollmachten', 'Testament', 'Bankdaten'],
    notificationEmail: 'max@example.com',
    status: 'active',
  },
  {
    id: '2',
    beneficiaryName: 'Anna Mustermann',
    accessType: 'date',
    triggerDate: '2030-01-01',
    triggerEvent: '01.01.2030',
    folders: ['Finanzplanung'],
    notificationEmail: 'anna@example.com',
    status: 'active',
  },
];

const ACCESS_TYPES = {
  death: 'Nach meinem Tod',
  incapacity: 'Bei Handlungsunfähigkeit',
  date: 'Ab festem Datum',
  emergency: 'Im Notfall (mit Verifikation)',
};

export function TimeControlledAccess(_props: TimeControlledAccessProps) {
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [accessRules, setAccessRules] = useState(mockAccessRules);
  const [formData, setFormData] = useState({
    beneficiaryEmail: '',
    accessType: 'death',
    triggerDate: '',
    selectedFolders: [] as string[],
  });

  // Mock-Ordner
  const folders = ['Vollmachten', 'Testament', 'Bankdaten', 'Finanzplanung', 'Versicherungen'];

  const handleAdd = () => {
    // Mock: Würde API aufrufen
    setShowAddDialog(false);
    setFormData({
      beneficiaryEmail: '',
      accessType: 'death',
      triggerDate: '',
      selectedFolders: [],
    });
  };

  const toggleRuleStatus = (ruleId: string) => {
    setAccessRules((rules) =>
      rules.map((r) =>
        r.id === ruleId
          ? { ...r, status: r.status === 'active' ? 'paused' : 'active' }
          : r
      )
    );
  };

  return (
    <div className="space-y-6">
      {/* Info-Banner */}
      <Alert>
        <Key className="h-4 w-4" />
        <AlertTitle>Zeitgesteuerter Zugriff</AlertTitle>
        <AlertDescription>
          Gewähren Sie ausgewählten Personen Zugriff auf bestimmte Ordner,
          der erst nach einem festgelegten Ereignis aktiviert wird.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Zugriffsregeln
              </CardTitle>
              <CardDescription>
                Konfigurieren Sie, wer wann auf welche Dokumente zugreifen kann
              </CardDescription>
            </div>
            <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
              <DialogTrigger asChild>
                <Button>
                  <Plus className="h-4 w-4 mr-2" />
                  Regel hinzufügen
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-lg">
                <DialogHeader>
                  <DialogTitle>Zugriffsregel erstellen</DialogTitle>
                  <DialogDescription>
                    Definieren Sie, wer unter welchen Bedingungen Zugriff erhält.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2">
                    <Label htmlFor="email">E-Mail des Begünstigten</Label>
                    <Input
                      id="email"
                      type="email"
                      value={formData.beneficiaryEmail}
                      onChange={(e) =>
                        setFormData({ ...formData, beneficiaryEmail: e.target.value })
                      }
                      placeholder="erbe@example.com"
                    />
                    <p className="text-xs text-muted-foreground">
                      Diese Person erhält eine Einladung und wird bei Aktivierung benachrichtigt.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label>Auslöser</Label>
                    <Select
                      value={formData.accessType}
                      onValueChange={(v) =>
                        setFormData({ ...formData, accessType: v })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(ACCESS_TYPES).map(([value, label]) => (
                          <SelectItem key={value} value={value}>
                            {label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {formData.accessType === 'date' && (
                    <div className="space-y-2">
                      <Label htmlFor="triggerDate">Aktivierungsdatum</Label>
                      <Input
                        id="triggerDate"
                        type="date"
                        value={formData.triggerDate}
                        onChange={(e) =>
                          setFormData({ ...formData, triggerDate: e.target.value })
                        }
                      />
                    </div>
                  )}

                  <div className="space-y-2">
                    <Label>Ordner freigeben</Label>
                    <div className="grid grid-cols-2 gap-2">
                      {folders.map((folder) => (
                        <label
                          key={folder}
                          className="flex items-center gap-2 p-2 border rounded cursor-pointer hover:bg-muted/50"
                        >
                          <input
                            type="checkbox"
                            checked={formData.selectedFolders.includes(folder)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setFormData({
                                  ...formData,
                                  selectedFolders: [...formData.selectedFolders, folder],
                                });
                              } else {
                                setFormData({
                                  ...formData,
                                  selectedFolders: formData.selectedFolders.filter(
                                    (f) => f !== folder
                                  ),
                                });
                              }
                            }}
                            className="rounded"
                          />
                          <span className="text-sm">{folder}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setShowAddDialog(false)}>
                    Abbrechen
                  </Button>
                  <Button onClick={handleAdd}>
                    Regel erstellen
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {accessRules.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Clock className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Noch keine Zugriffsregeln definiert</p>
              <p className="text-sm mt-1">
                Erstellen Sie Regeln für zeitgesteuerten Dokumentenzugriff.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {accessRules.map((rule) => (
                <div
                  key={rule.id}
                  className={`flex items-start justify-between p-4 border rounded-lg ${
                    rule.status === 'paused' ? 'opacity-60' : ''
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div
                      className={`p-2 rounded-lg ${
                        rule.status === 'active'
                          ? 'bg-green-100 dark:bg-green-900/30'
                          : 'bg-muted'
                      }`}
                    >
                      {rule.status === 'active' ? (
                        <Unlock className="h-5 w-5 text-green-600" />
                      ) : (
                        <Lock className="h-5 w-5 text-muted-foreground" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="font-medium">{rule.beneficiaryName}</h4>
                        <Badge
                          variant={rule.status === 'active' ? 'default' : 'secondary'}
                        >
                          {rule.status === 'active' ? 'Aktiv' : 'Pausiert'}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {rule.triggerEvent}
                        </span>
                        <span className="flex items-center gap-1">
                          <Users className="h-3 w-3" />
                          {rule.folders.length} Ordner
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {rule.folders.map((folder) => (
                          <Badge key={folder} variant="outline" className="text-xs">
                            {folder}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={rule.status === 'active'}
                      onCheckedChange={() => toggleRuleStatus(rule.id)}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Sicherheitshinweis */}
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Wichtiger Hinweis</AlertTitle>
        <AlertDescription>
          Der "Nach meinem Tod"-Auslöser erfordert eine Verifikation durch einen
          Notar oder eine behördliche Sterbeurkunde. Der Zugriff wird nicht
          automatisch gewährt, sondern muss von einem Administrator freigegeben werden.
        </AlertDescription>
      </Alert>
    </div>
  );
}

export default TimeControlledAccess;
