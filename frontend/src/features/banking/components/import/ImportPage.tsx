/**
 * Import Page
 * Banktransaktionen aus Dateien importieren
 */

import { useState, useCallback } from 'react';
import { Upload, FileText, ArrowRight, Loader2, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import {
    useAccounts,
    useImportPreview,
    useExecuteImport,
} from '@/features/banking/hooks/use-banking-queries';
import { ImportFormatSelector } from './ImportFormatSelector';
import { ImportPreview } from './ImportPreview';
import type { ImportFormat } from '@/lib/api/services/banking';

type ImportStep = 'upload' | 'preview' | 'importing' | 'success';

export function ImportPage() {
    const { toast } = useToast();
    const [step, setStep] = useState<ImportStep>('upload');
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [selectedFormat, setSelectedFormat] = useState<ImportFormat>('mt940');
    const [selectedAccount, setSelectedAccount] = useState<string>('');
    const [importedCount, setImportedCount] = useState(0);

    const { data: accounts } = useAccounts();
    const importPreview = useImportPreview();
    const executeImport = useExecuteImport();

    const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setSelectedFile(file);
            setStep('upload');
        }
    }, []);

    const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        const file = e.dataTransfer.files?.[0];
        if (file) {
            setSelectedFile(file);
            setStep('upload');
        }
    }, []);

    const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
    }, []);

    const handlePreview = async () => {
        if (!selectedFile || !selectedAccount) {
            toast({
                title: 'Fehlende Angaben',
                description: 'Bitte waehlen Sie eine Datei und ein Konto aus.',
                variant: 'destructive',
            });
            return;
        }

        try {
            await importPreview.mutateAsync({
                file: selectedFile,
                bankAccountId: selectedAccount,
                formatHint: selectedFormat,
            });
            setStep('preview');
        } catch (err) {
            toast({
                title: 'Vorschau fehlgeschlagen',
                description: err instanceof Error ? err.message : 'Unbekannter Fehler',
                variant: 'destructive',
            });
        }
    };

    const handleImport = async () => {
        if (!selectedFile || !selectedAccount) return;

        setStep('importing');

        try {
            const result = await executeImport.mutateAsync({
                file: selectedFile,
                bankAccountId: selectedAccount,
                formatHint: selectedFormat,
            });
            setImportedCount(result.transaction_count);
            setStep('success');
            toast({
                title: 'Import erfolgreich',
                description: `${result.transaction_count} Transaktionen wurden importiert.`,
            });
        } catch (err) {
            setStep('preview');
            toast({
                title: 'Import fehlgeschlagen',
                description: err instanceof Error ? err.message : 'Unbekannter Fehler',
                variant: 'destructive',
            });
        }
    };

    const handleReset = () => {
        setSelectedFile(null);
        setSelectedAccount('');
        setStep('upload');
        importPreview.reset();
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h2 className="text-2xl font-bold tracking-tight">Transaktionen importieren</h2>
                <p className="text-muted-foreground">
                    Importieren Sie Kontoauszuege aus verschiedenen Formaten.
                </p>
            </div>

            {/* Step Indicator */}
            <div className="flex items-center gap-2 text-sm">
                <span
                    className={`flex items-center gap-1 ${step === 'upload' ? 'text-primary font-medium' : 'text-muted-foreground'}`}
                >
                    1. Datei waehlen
                </span>
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
                <span
                    className={`flex items-center gap-1 ${step === 'preview' ? 'text-primary font-medium' : 'text-muted-foreground'}`}
                >
                    2. Vorschau pruefen
                </span>
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
                <span
                    className={`flex items-center gap-1 ${step === 'success' ? 'text-primary font-medium' : 'text-muted-foreground'}`}
                >
                    3. Importieren
                </span>
            </div>

            {/* Upload Step */}
            {step === 'upload' && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Upload className="h-5 w-5" />
                            Datei hochladen
                        </CardTitle>
                        <CardDescription>
                            Unterstuetzte Formate: MT940, CAMT.053, CSV (Sparkasse, Volksbank,
                            Generisch)
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        {/* Drop Zone */}
                        <div
                            className="border-2 border-dashed rounded-lg p-8 text-center hover:border-primary/50 transition-colors cursor-pointer"
                            onDrop={handleDrop}
                            onDragOver={handleDragOver}
                            onClick={() => document.getElementById('file-input')?.click()}
                        >
                            <input
                                id="file-input"
                                type="file"
                                className="hidden"
                                accept=".mt940,.sta,.xml,.csv,.txt"
                                onChange={handleFileSelect}
                            />
                            {selectedFile ? (
                                <div className="flex flex-col items-center gap-2">
                                    <FileText className="h-12 w-12 text-primary" />
                                    <p className="font-medium">{selectedFile.name}</p>
                                    <p className="text-sm text-muted-foreground">
                                        {(selectedFile.size / 1024).toFixed(1)} KB
                                    </p>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setSelectedFile(null);
                                        }}
                                    >
                                        Andere Datei waehlen
                                    </Button>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-2">
                                    <Upload className="h-12 w-12 text-muted-foreground" />
                                    <p className="font-medium">
                                        Datei hierher ziehen oder klicken zum Auswaehlen
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        MT940, CAMT.053 oder CSV-Datei
                                    </p>
                                </div>
                            )}
                        </div>

                        {/* Settings */}
                        <div className="grid gap-4 md:grid-cols-2">
                            <ImportFormatSelector
                                value={selectedFormat}
                                onChange={setSelectedFormat}
                            />

                            <div className="space-y-2">
                                <Label>Zielkonto</Label>
                                <Select value={selectedAccount} onValueChange={setSelectedAccount}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Konto waehlen..." />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {accounts?.map((account) => (
                                            <SelectItem key={account.id} value={account.id}>
                                                {account.account_name} ({account.iban.slice(-4)})
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        {/* Actions */}
                        <div className="flex justify-end">
                            <Button
                                onClick={handlePreview}
                                disabled={!selectedFile || !selectedAccount || importPreview.isPending}
                            >
                                {importPreview.isPending ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Analysiere...
                                    </>
                                ) : (
                                    <>
                                        Vorschau anzeigen
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </>
                                )}
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Preview Step */}
            {step === 'preview' && importPreview.data && (
                <div className="space-y-4">
                    <ImportPreview preview={importPreview.data} />

                    <div className="flex justify-between">
                        <Button variant="outline" onClick={handleReset}>
                            Zurueck
                        </Button>
                        <Button
                            onClick={handleImport}
                            disabled={importPreview.data.transaction_count === 0}
                        >
                            {importPreview.data.transaction_count} Transaktionen importieren
                            <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                    </div>
                </div>
            )}

            {/* Importing Step */}
            {step === 'importing' && (
                <Card>
                    <CardContent className="py-12">
                        <div className="flex flex-col items-center gap-4">
                            <Loader2 className="h-12 w-12 animate-spin text-primary" />
                            <p className="text-lg font-medium">Transaktionen werden importiert...</p>
                            <p className="text-muted-foreground">
                                Bitte warten Sie, dies kann einen Moment dauern.
                            </p>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Success Step */}
            {step === 'success' && (
                <Card>
                    <CardContent className="py-12">
                        <div className="flex flex-col items-center gap-4">
                            <CheckCircle className="h-12 w-12 text-green-600" />
                            <p className="text-lg font-medium">Import erfolgreich!</p>
                            <p className="text-muted-foreground">
                                {importedCount} Transaktionen wurden importiert.
                            </p>
                            <div className="flex gap-2">
                                <Button variant="outline" onClick={handleReset}>
                                    Weitere Datei importieren
                                </Button>
                                <Button asChild>
                                    <a href="/admin/banking/transactions">Zu den Transaktionen</a>
                                </Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
