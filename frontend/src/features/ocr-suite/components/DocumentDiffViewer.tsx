import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useDocumentVersions } from '../hooks/use-ocr-suite-queries';
import { GitCompare } from 'lucide-react';

interface DocumentDiffViewerProps {
  documentId: string;
}

export function DocumentDiffViewer({ documentId }: DocumentDiffViewerProps) {
  const [version1Id, setVersion1Id] = useState<string>('');
  const [version2Id, setVersion2Id] = useState<string>('');

  const { data: versions, isLoading } = useDocumentVersions(documentId);

  const version1 = versions?.find((v) => v.id === version1Id);
  const version2 = versions?.find((v) => v.id === version2Id);

  const computeDiff = (text1: string, text2: string) => {
    const lines1 = text1.split('\n');
    const lines2 = text2.split('\n');

    const maxLength = Math.max(lines1.length, lines2.length);
    const diff: Array<{
      line1: string;
      line2: string;
      status: 'same' | 'modified' | 'added' | 'removed';
    }> = [];

    for (let i = 0; i < maxLength; i++) {
      const l1 = lines1[i] || '';
      const l2 = lines2[i] || '';

      if (l1 === l2) {
        diff.push({ line1: l1, line2: l2, status: 'same' });
      } else if (l1 && !l2) {
        diff.push({ line1: l1, line2: '', status: 'removed' });
      } else if (!l1 && l2) {
        diff.push({ line1: '', line2: l2, status: 'added' });
      } else {
        diff.push({ line1: l1, line2: l2, status: 'modified' });
      }
    }

    return diff;
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Dokument-Vergleich</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Lade Versionen...</p>
        </CardContent>
      </Card>
    );
  }

  if (!versions || versions.length < 2) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Dokument-Vergleich</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Mindestens zwei Versionen erforderlich für einen Vergleich.
          </p>
        </CardContent>
      </Card>
    );
  }

  const diff = version1 && version2 ? computeDiff(version1.ocrText, version2.ocrText) : null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitCompare className="w-5 h-5" />
            Dokument-Vergleich
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Version 1</label>
              <Select value={version1Id || undefined} onValueChange={setVersion1Id}>
                <SelectTrigger>
                  <SelectValue placeholder="Version wählen..." />
                </SelectTrigger>
                <SelectContent>
                  {versions.map((version) => (
                    <SelectItem key={version.id} value={version.id}>
                      Version {version.versionNumber} ({new Date(version.createdAt).toLocaleDateString('de-DE')})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Version 2</label>
              <Select value={version2Id || undefined} onValueChange={setVersion2Id}>
                <SelectTrigger>
                  <SelectValue placeholder="Version wählen..." />
                </SelectTrigger>
                <SelectContent>
                  {versions.map((version) => (
                    <SelectItem key={version.id} value={version.id}>
                      Version {version.versionNumber} ({new Date(version.createdAt).toLocaleDateString('de-DE')})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {diff && (
        <Card>
          <CardHeader>
            <CardTitle>Unterschiede</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 font-mono text-sm">
              <div className="space-y-1">
                <h3 className="font-semibold mb-2">Version {version1?.versionNumber}</h3>
                {diff.map((line, idx) => (
                  <div
                    key={idx}
                    className={`px-2 py-1 ${
                      line.status === 'removed'
                        ? 'bg-red-100 dark:bg-red-900/20 text-red-800 dark:text-red-300'
                        : line.status === 'modified'
                          ? 'bg-yellow-100 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-300'
                          : ''
                    }`}
                  >
                    {line.line1 || '\u00A0'}
                  </div>
                ))}
              </div>
              <div className="space-y-1">
                <h3 className="font-semibold mb-2">Version {version2?.versionNumber}</h3>
                {diff.map((line, idx) => (
                  <div
                    key={idx}
                    className={`px-2 py-1 ${
                      line.status === 'added'
                        ? 'bg-green-100 dark:bg-green-900/20 text-green-800 dark:text-green-300'
                        : line.status === 'modified'
                          ? 'bg-yellow-100 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-300'
                          : ''
                    }`}
                  >
                    {line.line2 || '\u00A0'}
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {!diff && (version1Id || version2Id) && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground text-center">
              Bitte wählen Sie beide Versionen aus, um den Vergleich anzuzeigen.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
