/**
 * EInvoiceGeneratorDialog - Dialog zum Generieren von E-Rechnungen.
 *
 * Features:
 * - ZUGFeRD PDF Generierung mit Profil-Auswahl
 * - XRechnung XML Generierung (CII/UBL)
 * - Mustang Service Health-Check für UBL
 */

import { useState } from "react";
import {
    FileText,
    FileCode,
    Loader2,
    CheckCircle2,
    AlertTriangle,
    Info,
} from "lucide-react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs";
import {
    useGenerateZugferd,
    useGenerateXrechnung,
    useMustangHealth,
} from "../hooks/useEInvoice";
import {
    PROFILE_LABELS,
    SYNTAX_LABELS,
    type ZUGFeRDProfile,
    type XRechnungSyntax,
} from "../types/einvoice.types";

interface EInvoiceGeneratorDialogProps {
    documentId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSuccess?: () => void;
}

const ZUGFERD_PROFILES: ZUGFeRDProfile[] = [
    'EN16931',
    'EXTENDED',
    'BASIC',
    'MINIMUM',
];

export function EInvoiceGeneratorDialog({
    documentId,
    open,
    onOpenChange,
    onSuccess,
}: EInvoiceGeneratorDialogProps) {
    const [activeTab, setActiveTab] = useState<'zugferd' | 'xrechnung'>('zugferd');
    const [selectedProfile, setSelectedProfile] = useState<ZUGFeRDProfile>('EN16931');
    const [selectedSyntax, setSelectedSyntax] = useState<XRechnungSyntax>('CII');

    const { data: mustangHealth, isLoading: isHealthLoading } = useMustangHealth();
    const generateZugferd = useGenerateZugferd();
    const generateXrechnung = useGenerateXrechnung();

    const isUblAvailable = mustangHealth?.available && mustangHealth?.features?.xrechnungUbl;

    const handleGenerate = async () => {
        try {
            if (activeTab === 'zugferd') {
                await generateZugferd.mutateAsync({
                    documentId,
                    profile: selectedProfile,
                });
            } else {
                await generateXrechnung.mutateAsync({
                    documentId,
                    syntax: selectedSyntax,
                });
            }
            onSuccess?.();
            onOpenChange(false);
        } catch (error) {
            console.error('E-Invoice generation failed:', error);
        }
    };

    const isPending = generateZugferd.isPending || generateXrechnung.isPending;
    const isError = generateZugferd.isError || generateXrechnung.isError;
    const errorMessage = generateZugferd.error?.message || generateXrechnung.error?.message;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FileCode className="h-5 w-5" />
                        E-Rechnung generieren
                    </DialogTitle>
                    <DialogDescription>
                        Generieren Sie eine E-Rechnung im ZUGFeRD- oder XRechnung-Format.
                    </DialogDescription>
                </DialogHeader>

                <Tabs
                    value={activeTab}
                    onValueChange={(v) => setActiveTab(v as 'zugferd' | 'xrechnung')}
                >
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="zugferd" className="flex items-center gap-2">
                            <FileText className="h-4 w-4" />
                            ZUGFeRD PDF
                        </TabsTrigger>
                        <TabsTrigger value="xrechnung" className="flex items-center gap-2">
                            <FileCode className="h-4 w-4" />
                            XRechnung XML
                        </TabsTrigger>
                    </TabsList>

                    {/* ZUGFeRD Tab */}
                    <TabsContent value="zugferd" className="space-y-4 mt-4">
                        <div className="space-y-2">
                            <Label>Profil wählen</Label>
                            <Select
                                value={selectedProfile}
                                onValueChange={(v) => setSelectedProfile(v as ZUGFeRDProfile)}
                            >
                                <SelectTrigger>
                                    <SelectValue placeholder="Profil wählen" />
                                </SelectTrigger>
                                <SelectContent>
                                    {ZUGFERD_PROFILES.map((profile) => (
                                        <SelectItem key={profile} value={profile}>
                                            <div className="flex items-center justify-between w-full">
                                                <span>{PROFILE_LABELS[profile]}</span>
                                                {profile === 'EN16931' && (
                                                    <Badge variant="secondary" className="ml-2 text-xs">
                                                        Empfohlen
                                                    </Badge>
                                                )}
                                            </div>
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <Alert>
                            <Info className="h-4 w-4" />
                            <AlertTitle>ZUGFeRD 2.x</AlertTitle>
                            <AlertDescription>
                                Erzeugt eine PDF/A-3 Datei mit eingebettetem XML.
                                Kompatibel mit B2B-Austausch und den meisten Buchhaltungssystemen.
                            </AlertDescription>
                        </Alert>
                    </TabsContent>

                    {/* XRechnung Tab */}
                    <TabsContent value="xrechnung" className="space-y-4 mt-4">
                        <div className="space-y-2">
                            <Label>XML-Syntax wählen</Label>
                            <RadioGroup
                                value={selectedSyntax}
                                onValueChange={(v: string) => setSelectedSyntax(v as XRechnungSyntax)}
                                className="space-y-2"
                            >
                                <div className="flex items-center space-x-2">
                                    <RadioGroupItem value="CII" id="cii" />
                                    <Label htmlFor="cii" className="flex-1 cursor-pointer">
                                        <div className="flex items-center justify-between">
                                            <span>{SYNTAX_LABELS.CII}</span>
                                            <Badge variant="secondary" className="text-xs">
                                                Empfohlen
                                            </Badge>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            UN/CEFACT Cross Industry Invoice - Standard für Deutschland
                                        </p>
                                    </Label>
                                </div>
                                <div className="flex items-center space-x-2">
                                    <RadioGroupItem
                                        value="UBL"
                                        id="ubl"
                                        disabled={!isUblAvailable}
                                    />
                                    <Label
                                        htmlFor="ubl"
                                        className={`flex-1 ${!isUblAvailable ? 'opacity-50' : 'cursor-pointer'}`}
                                    >
                                        <div className="flex items-center justify-between">
                                            <span>{SYNTAX_LABELS.UBL}</span>
                                            {!isUblAvailable && (
                                                <Badge variant="outline" className="text-xs">
                                                    Nicht verfügbar
                                                </Badge>
                                            )}
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            Universal Business Language 2.1 - Erfordert Mustang Service
                                        </p>
                                    </Label>
                                </div>
                            </RadioGroup>
                        </div>

                        {/* Mustang Status */}
                        <MustangStatusAlert
                            isLoading={isHealthLoading}
                            health={mustangHealth}
                        />

                        <Alert>
                            <Info className="h-4 w-4" />
                            <AlertTitle>XRechnung 3.0.2</AlertTitle>
                            <AlertDescription>
                                Für B2G (Business-to-Government) Rechnungen an öffentliche Auftraggeber.
                                Erfordert Leitweg-ID im Dokument.
                            </AlertDescription>
                        </Alert>
                    </TabsContent>
                </Tabs>

                {/* Error Display */}
                {isError && (
                    <Alert variant="destructive">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle>Fehler</AlertTitle>
                        <AlertDescription>
                            {errorMessage || 'E-Rechnung konnte nicht generiert werden.'}
                        </AlertDescription>
                    </Alert>
                )}

                <DialogFooter>
                    <Button
                        variant="outline"
                        onClick={() => onOpenChange(false)}
                        disabled={isPending}
                    >
                        Abbrechen
                    </Button>
                    <Button
                        onClick={handleGenerate}
                        disabled={isPending || (activeTab === 'xrechnung' && selectedSyntax === 'UBL' && !isUblAvailable)}
                    >
                        {isPending ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Generiere...
                            </>
                        ) : (
                            <>
                                <FileCode className="h-4 w-4 mr-2" />
                                Generieren & Herunterladen
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// Mustang Status Alert
function MustangStatusAlert({
    isLoading,
    health,
}: {
    isLoading: boolean;
    health?: {
        status: string;
        available: boolean;
        mustangVersion?: string;
        error?: string;
    };
}) {
    if (isLoading) {
        return (
            <Alert>
                <Loader2 className="h-4 w-4 animate-spin" />
                <AlertTitle>Mustang Service</AlertTitle>
                <AlertDescription>Prüfe Verfügbarkeit...</AlertDescription>
            </Alert>
        );
    }

    if (!health?.available) {
        return (
            <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Mustang Service nicht verfügbar</AlertTitle>
                <AlertDescription>
                    UBL-Generierung erfordert den Mustang Microservice.
                    {health?.error && <p className="mt-1 text-xs">{health.error}</p>}
                </AlertDescription>
            </Alert>
        );
    }

    return (
        <Alert className="border-green-200 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <AlertTitle>Mustang Service verfügbar</AlertTitle>
            <AlertDescription>
                Version: {health.mustangVersion || 'Unbekannt'}
            </AlertDescription>
        </Alert>
    );
}
