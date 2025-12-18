/**
 * EInvoiceValidator - Komponente zur E-Invoice Validierung.
 *
 * Features:
 * - Datei-Upload für Validierung
 * - Validator-Auswahl (factur-x, KoSIT, Mustang)
 * - Detaillierte Fehler- und Warnungsanzeige
 */

import { useState, useCallback } from "react";
import {
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Upload,
    Loader2,
    FileText,
    ChevronDown,
    ChevronUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useValidateEInvoice, useMustangHealth } from "../hooks/useEInvoice";
import { VALIDATOR_LABELS, type ValidatorType, type ValidationError } from "../types/einvoice.types";

interface EInvoiceValidatorProps {
    className?: string;
}

const VALIDATORS: ValidatorType[] = ['AUTO', 'FACTURX', 'KOSIT', 'MUSTANG'];

export function EInvoiceValidator({ className }: EInvoiceValidatorProps) {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [selectedValidator, setSelectedValidator] = useState<ValidatorType>('AUTO');
    const [errorsExpanded, setErrorsExpanded] = useState(true);
    const [warningsExpanded, setWarningsExpanded] = useState(false);

    const { data: mustangHealth } = useMustangHealth();
    const validateMutation = useValidateEInvoice();

    const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setSelectedFile(file);
            validateMutation.reset();
        }
    }, [validateMutation]);

    const handleValidate = async () => {
        if (!selectedFile) return;

        await validateMutation.mutateAsync({
            file: selectedFile,
            validator: selectedValidator,
        });
    };

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        if (file && (file.name.endsWith('.xml') || file.name.endsWith('.pdf'))) {
            setSelectedFile(file);
            validateMutation.reset();
        }
    }, [validateMutation]);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
    }, []);

    const result = validateMutation.data;
    const isKositAvailable = mustangHealth?.available;

    return (
        <Card className={className}>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    E-Rechnung validieren
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* File Upload Area */}
                <div
                    className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onClick={() => document.getElementById('validator-file-input')?.click()}
                >
                    <input
                        id="validator-file-input"
                        type="file"
                        accept=".xml,.pdf"
                        className="hidden"
                        onChange={handleFileChange}
                    />
                    <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                    {selectedFile ? (
                        <div>
                            <p className="text-sm font-medium">{selectedFile.name}</p>
                            <p className="text-xs text-muted-foreground">
                                {(selectedFile.size / 1024).toFixed(1)} KB
                            </p>
                        </div>
                    ) : (
                        <div>
                            <p className="text-sm text-muted-foreground">
                                Datei hierher ziehen oder klicken
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                                XML oder PDF (ZUGFeRD)
                            </p>
                        </div>
                    )}
                </div>

                {/* Validator Selection */}
                <div className="space-y-2">
                    <Label>Validator</Label>
                    <Select
                        value={selectedValidator}
                        onValueChange={(v) => setSelectedValidator(v as ValidatorType)}
                    >
                        <SelectTrigger>
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {VALIDATORS.map((validator) => (
                                <SelectItem
                                    key={validator}
                                    value={validator}
                                    disabled={
                                        (validator === 'KOSIT' || validator === 'MUSTANG') &&
                                        !isKositAvailable
                                    }
                                >
                                    <div className="flex items-center gap-2">
                                        <span>{VALIDATOR_LABELS[validator]}</span>
                                        {(validator === 'KOSIT' || validator === 'MUSTANG') &&
                                            !isKositAvailable && (
                                                <Badge variant="outline" className="text-xs">
                                                    Offline
                                                </Badge>
                                            )}
                                    </div>
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                {/* Validate Button */}
                <Button
                    className="w-full"
                    onClick={handleValidate}
                    disabled={!selectedFile || validateMutation.isPending}
                >
                    {validateMutation.isPending ? (
                        <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Validiere...
                        </>
                    ) : (
                        <>
                            <CheckCircle2 className="h-4 w-4 mr-2" />
                            Validieren
                        </>
                    )}
                </Button>

                {/* Validation Result */}
                {result && (
                    <ValidationResultDisplay
                        result={result}
                        errorsExpanded={errorsExpanded}
                        warningsExpanded={warningsExpanded}
                        onErrorsToggle={() => setErrorsExpanded(!errorsExpanded)}
                        onWarningsToggle={() => setWarningsExpanded(!warningsExpanded)}
                    />
                )}

                {/* Error State */}
                {validateMutation.isError && (
                    <Alert variant="destructive">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle>Validierung fehlgeschlagen</AlertTitle>
                        <AlertDescription>
                            {validateMutation.error?.message || 'Unbekannter Fehler'}
                        </AlertDescription>
                    </Alert>
                )}
            </CardContent>
        </Card>
    );
}

// Validation Result Display
function ValidationResultDisplay({
    result,
    errorsExpanded,
    warningsExpanded,
    onErrorsToggle,
    onWarningsToggle,
}: {
    result: {
        valid: boolean;
        validatorUsed: string;
        schemaValid: boolean;
        schematronValid: boolean;
        pdfACompliant: boolean | null;
        errors: ValidationError[];
        warnings: ValidationError[];
        errorCount: number;
        warningCount: number;
    };
    errorsExpanded: boolean;
    warningsExpanded: boolean;
    onErrorsToggle: () => void;
    onWarningsToggle: () => void;
}) {
    return (
        <div className="space-y-4">
            {/* Overall Result */}
            <Alert
                className={
                    result.valid
                        ? "border-green-200 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100"
                        : ""
                }
                variant={result.valid ? undefined : "destructive"}
            >
                {result.valid ? (
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                ) : (
                    <XCircle className="h-4 w-4" />
                )}
                <AlertTitle>
                    {result.valid ? "Validierung erfolgreich" : "Validierung fehlgeschlagen"}
                </AlertTitle>
                <AlertDescription>
                    Validator: {result.validatorUsed}
                </AlertDescription>
            </Alert>

            {/* Detail Badges */}
            <div className="flex flex-wrap gap-2">
                <Badge variant={result.schemaValid ? "default" : "destructive"}>
                    Schema: {result.schemaValid ? "OK" : "Fehler"}
                </Badge>
                <Badge variant={result.schematronValid ? "default" : "destructive"}>
                    Schematron: {result.schematronValid ? "OK" : "Fehler"}
                </Badge>
                {result.pdfACompliant !== null && (
                    <Badge variant={result.pdfACompliant ? "default" : "secondary"}>
                        PDF/A-3: {result.pdfACompliant ? "OK" : "Nicht geprueft"}
                    </Badge>
                )}
            </div>

            {/* Errors */}
            {result.errorCount > 0 && (
                <Collapsible open={errorsExpanded} onOpenChange={onErrorsToggle}>
                    <CollapsibleTrigger asChild>
                        <Button variant="ghost" className="w-full justify-between">
                            <span className="flex items-center gap-2">
                                <XCircle className="h-4 w-4 text-destructive" />
                                {result.errorCount} Fehler
                            </span>
                            {errorsExpanded ? (
                                <ChevronUp className="h-4 w-4" />
                            ) : (
                                <ChevronDown className="h-4 w-4" />
                            )}
                        </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                        <div className="space-y-2 mt-2">
                            {result.errors.map((error, idx) => (
                                <ValidationMessage key={idx} message={error} type="error" />
                            ))}
                        </div>
                    </CollapsibleContent>
                </Collapsible>
            )}

            {/* Warnings */}
            {result.warningCount > 0 && (
                <Collapsible open={warningsExpanded} onOpenChange={onWarningsToggle}>
                    <CollapsibleTrigger asChild>
                        <Button variant="ghost" className="w-full justify-between">
                            <span className="flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4 text-yellow-600" />
                                {result.warningCount} Warnungen
                            </span>
                            {warningsExpanded ? (
                                <ChevronUp className="h-4 w-4" />
                            ) : (
                                <ChevronDown className="h-4 w-4" />
                            )}
                        </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                        <div className="space-y-2 mt-2">
                            {result.warnings.map((warning, idx) => (
                                <ValidationMessage key={idx} message={warning} type="warning" />
                            ))}
                        </div>
                    </CollapsibleContent>
                </Collapsible>
            )}
        </div>
    );
}

// Single Validation Message
function ValidationMessage({
    message,
    type,
}: {
    message: ValidationError;
    type: 'error' | 'warning';
}) {
    return (
        <div
            className={`p-3 rounded-lg text-sm ${
                type === 'error'
                    ? 'bg-destructive/10 border border-destructive/20'
                    : 'bg-yellow-50 border border-yellow-200 dark:bg-yellow-950 dark:border-yellow-800'
            }`}
        >
            <div className="flex items-start gap-2">
                {type === 'error' ? (
                    <XCircle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                ) : (
                    <AlertTriangle className="h-4 w-4 text-yellow-600 mt-0.5 shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="outline" className="text-xs">
                            {message.code}
                        </Badge>
                        {message.ruleId && (
                            <Badge variant="secondary" className="text-xs">
                                {message.ruleId}
                            </Badge>
                        )}
                    </div>
                    <p className="mt-1 break-words">{message.message}</p>
                    {message.location && (
                        <p className="text-xs text-muted-foreground mt-1">
                            Position: {message.location}
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}
