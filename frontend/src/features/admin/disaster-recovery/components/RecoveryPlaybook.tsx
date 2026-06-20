/**
 * Recovery Playbook
 *
 * Generiert step-by-step Recovery-Anweisungen für verschiedene Disaster-Szenarien.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { BookOpen, Download, Clock, User, CheckCircle2, FileText, Phone, Mail, ChevronRight, Terminal } from 'lucide-react';
import { useGeneratePlaybook } from '../hooks';
import type { RecoveryPlaybook as RecoveryPlaybookType } from '../api';

const disasterTypes: Array<{
  value: RecoveryPlaybookType['disaster_type'];
  label: string;
  description: string;
}> = [
  {
    value: 'hardware_failure',
    label: 'Hardware-Ausfall',
    description: 'Server, Storage oder Netzwerk-Ausfall',
  },
  {
    value: 'data_corruption',
    label: 'Datenkorruption',
    description: 'Beschädigte Datenbank oder Dateisystem',
  },
  {
    value: 'ransomware',
    label: 'Ransomware-Angriff',
    description: 'Verschlüsselung durch Malware',
  },
  {
    value: 'natural_disaster',
    label: 'Naturkatastrophe',
    description: 'Feuer, Hochwasser, Sturm',
  },
  {
    value: 'human_error',
    label: 'Menschlicher Fehler',
    description: 'Versehentliches Löschen oder Konfigurationsfehler',
  },
];

const severityLevels: Array<{
  value: RecoveryPlaybookType['severity_level'];
  label: string;
  variant: 'default' | 'destructive' | 'outline' | 'secondary';
}> = [
  { value: 'critical', label: 'Kritisch', variant: 'destructive' },
  { value: 'high', label: 'Hoch', variant: 'destructive' },
  { value: 'medium', label: 'Mittel', variant: 'secondary' },
  { value: 'low', label: 'Niedrig', variant: 'outline' },
];

const categoryIcons = {
  preparation: FileText,
  execution: Terminal,
  validation: CheckCircle2,
  communication: Phone,
};

const categoryLabels = {
  preparation: 'Vorbereitung',
  execution: 'Ausführung',
  validation: 'Validierung',
  communication: 'Kommunikation',
};

export function RecoveryPlaybook() {
  const [disasterType, setDisasterType] =
    useState<RecoveryPlaybookType['disaster_type']>('hardware_failure');
  const [severityLevel, setSeverityLevel] =
    useState<RecoveryPlaybookType['severity_level']>('high');
  const [playbook, setPlaybook] = useState<RecoveryPlaybookType | null>(null);

  const generateMutation = useGeneratePlaybook();

  const handleGenerate = async () => {
    const result = await generateMutation.mutateAsync({ disaster_type: disasterType, severity_level: severityLevel });
    setPlaybook(result);
  };

  const handleDownload = () => {
    if (!playbook) return;

    // Create text file content
    let content = `DISASTER RECOVERY PLAYBOOK\n\n`;
    content += `Typ: ${disasterTypes.find((t) => t.value === playbook.disaster_type)?.label}\n`;
    content += `Schweregrad: ${
      severityLevels.find((s) => s.value === playbook.severity_level)?.label
    }\n`;
    content += `Geschätzte Gesamtdauer: ${(playbook.total_estimated_duration_minutes / 60).toFixed(1)} Stunden\n`;
    content += `Generiert: ${new Date(playbook.generated_at).toLocaleString('de-DE')}\n\n`;

    content += `${'='.repeat(80)}\n`;
    content += `RECOVERY-SCHRITTE\n`;
    content += `${'='.repeat(80)}\n\n`;

    playbook.steps.forEach((step) => {
      content += `${step.step_number}. ${step.title}\n`;
      content += `   Kategorie: ${categoryLabels[step.category]}\n`;
      content += `   Dauer: ${step.estimated_duration_minutes} Minuten\n`;
      content += `   Verantwortlich: ${step.responsible_role}\n\n`;
      content += `   ${step.description}\n\n`;

      if (step.prerequisites.length > 0) {
        content += `   Voraussetzungen:\n`;
        step.prerequisites.forEach((pre) => {
          content += `   - ${pre}\n`;
        });
        content += `\n`;
      }

      if (step.commands && step.commands.length > 0) {
        content += `   Befehle:\n`;
        step.commands.forEach((cmd) => {
          content += `   $ ${cmd}\n`;
        });
        content += `\n`;
      }

      content += `   Validierung:\n`;
      step.validation_criteria.forEach((criteria) => {
        content += `   ✓ ${criteria}\n`;
      });
      content += `\n${'-'.repeat(80)}\n\n`;
    });

    content += `${'='.repeat(80)}\n`;
    content += `NOTFALLKONTAKTE\n`;
    content += `${'='.repeat(80)}\n\n`;

    playbook.emergency_contacts.forEach((contact) => {
      content += `${contact.role}:\n`;
      if (contact.name) content += `  Name: ${contact.name}\n`;
      if (contact.phone) content += `  Telefon: ${contact.phone}\n`;
      if (contact.email) content += `  E-Mail: ${contact.email}\n`;
      content += `\n`;
    });

    // Download
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `recovery-playbook-${playbook.disaster_type}-${Date.now()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpen className="h-5 w-5" />
          Recovery-Playbook Generator
        </CardTitle>
        <CardDescription>
          Erstellen Sie detaillierte Wiederherstellungsanleitungen für verschiedene
          Disaster-Szenarien
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Configuration */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Disaster-Typ</label>
            <Select
              value={disasterType}
              onValueChange={(v) => setDisasterType(v as RecoveryPlaybookType['disaster_type'])}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {disasterTypes.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    <div>
                      <div className="font-medium">{type.label}</div>
                      <div className="text-xs text-muted-foreground">{type.description}</div>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Schweregrad</label>
            <Select
              value={severityLevel}
              onValueChange={(v) => setSeverityLevel(v as RecoveryPlaybookType['severity_level'])}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {severityLevels.map((level) => (
                  <SelectItem key={level.value} value={level.value}>
                    {level.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex gap-2">
          <Button onClick={handleGenerate} disabled={generateMutation.isPending}>
            {generateMutation.isPending ? 'Generiere...' : 'Playbook generieren'}
          </Button>
          {playbook && (
            <Button variant="outline" onClick={handleDownload}>
              <Download className="h-4 w-4 mr-2" />
              Als Textdatei
            </Button>
          )}
        </div>

        {/* Playbook Display */}
        {playbook && (
          <div className="space-y-4 pt-4 border-t">
            {/* Header Info */}
            <div className="flex items-center justify-between p-4 rounded-lg bg-muted">
              <div>
                <h3 className="font-semibold">
                  {disasterTypes.find((t) => t.value === playbook.disaster_type)?.label}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {disasterTypes.find((t) => t.value === playbook.disaster_type)?.description}
                </p>
              </div>
              <div className="text-right">
                <Badge
                  variant={
                    severityLevels.find((s) => s.value === playbook.severity_level)?.variant
                  }
                >
                  {severityLevels.find((s) => s.value === playbook.severity_level)?.label}
                </Badge>
                <div className="flex items-center gap-1 mt-2 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  Geschätzt: {(playbook.total_estimated_duration_minutes / 60).toFixed(1)}h
                </div>
              </div>
            </div>

            {/* Steps */}
            <div className="space-y-3">
              {playbook.steps.map((step) => {
                const CategoryIcon = categoryIcons[step.category];
                return (
                  <Card key={step.step_number}>
                    <CardContent className="pt-6">
                      <div className="flex items-start gap-4">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground font-semibold shrink-0">
                          {step.step_number}
                        </div>
                        <div className="flex-1 space-y-3">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <h4 className="font-semibold">{step.title}</h4>
                              <p className="text-sm text-muted-foreground mt-1">
                                {step.description}
                              </p>
                            </div>
                            <div className="flex flex-col items-end gap-2 shrink-0">
                              <Badge variant="outline" className="gap-1">
                                <CategoryIcon className="h-3 w-3" />
                                {categoryLabels[step.category]}
                              </Badge>
                              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                <Clock className="h-3 w-3" />
                                {step.estimated_duration_minutes}m
                              </div>
                              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                <User className="h-3 w-3" />
                                {step.responsible_role}
                              </div>
                            </div>
                          </div>

                          {step.prerequisites.length > 0 && (
                            <div className="text-sm">
                              <div className="font-medium mb-1">Voraussetzungen:</div>
                              <ul className="space-y-1 ml-4">
                                {step.prerequisites.map((pre, _i) => (
                                  <li key={pre} className="flex items-start gap-2">
                                    <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                                    <span className="text-muted-foreground">{pre}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {step.commands && step.commands.length > 0 && (
                            <div className="text-sm">
                              <div className="font-medium mb-1">Befehle:</div>
                              <div className="space-y-1">
                                {step.commands.map((cmd, _i) => (
                                  <code
                                    key={cmd}
                                    className="block bg-muted px-3 py-2 rounded text-xs font-mono"
                                  >
                                    $ {cmd}
                                  </code>
                                ))}
                              </div>
                            </div>
                          )}

                          <div className="text-sm">
                            <div className="font-medium mb-1">Validierung:</div>
                            <div className="space-y-1">
                              {step.validation_criteria.map((criteria, _i) => (
                                <div key={criteria} className="flex items-start gap-2">
                                  <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0 mt-0.5" />
                                  <span className="text-muted-foreground">{criteria}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            {/* Emergency Contacts */}
            <Alert>
              <Phone className="h-4 w-4" />
              <AlertTitle>Notfallkontakte</AlertTitle>
              <AlertDescription>
                <div className="mt-2 space-y-2">
                  {playbook.emergency_contacts.map((contact, _i) => (
                    <div key={contact.role} className="flex items-center justify-between text-sm">
                      <span className="font-medium">{contact.role}</span>
                      <div className="flex items-center gap-4 text-muted-foreground">
                        {contact.phone && (
                          <div className="flex items-center gap-1">
                            <Phone className="h-3 w-3" />
                            {contact.phone}
                          </div>
                        )}
                        {contact.email && (
                          <div className="flex items-center gap-1">
                            <Mail className="h-3 w-3" />
                            {contact.email}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </AlertDescription>
            </Alert>

            {/* Additional Resources */}
            {playbook.additional_resources.length > 0 && (
              <div className="pt-4 border-t">
                <h4 className="font-semibold mb-2">Zusätzliche Ressourcen</h4>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  {playbook.additional_resources.map((resource, _i) => (
                    <li key={resource} className="flex items-start gap-2">
                      <ChevronRight className="h-4 w-4 shrink-0 mt-0.5" />
                      {resource}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
