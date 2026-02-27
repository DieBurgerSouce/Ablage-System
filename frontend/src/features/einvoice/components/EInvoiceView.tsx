/**
 * EInvoiceView - E-Rechnungen Uebersichtsseite.
 *
 * Features:
 * - Tab "Uebersicht": KPI-Cards, Quick Actions, Info-Bereich
 * - Tab "Validierung": EInvoiceValidator eingebettet
 * - Tab "Formate": Unterstuetzte Formate mit Profilen und B2G-Badges
 */

import { useState } from "react";
import {
    FileCode,
    CheckCircle2,
    AlertTriangle,
    Heart,
    XCircle,
    Loader2,
    FileText,
    Upload,
    ListChecks,
    Shield,
    Info,
    ExternalLink,
    RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { EInvoiceValidator } from "./EInvoiceValidator";
import {
    useEInvoiceFormats,
    useMustangHealth,
} from "../hooks/useEInvoice";
import {
    PROFILE_LABELS,
    type ZUGFeRDProfile,
    type SupportedFormat,
} from "../types/einvoice.types";

interface EInvoiceViewProps {
    className?: string;
}

export function EInvoiceView({ className }: EInvoiceViewProps) {
    const [activeTab, setActiveTab] = useState("uebersicht");

    return (
        <div className={cn("space-y-6", className)}>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList>
                    <TabsTrigger value="uebersicht" className="flex items-center gap-2">
                        <ListChecks className="h-4 w-4" />
                        Uebersicht
                    </TabsTrigger>
                    <TabsTrigger value="validierung" className="flex items-center gap-2">
                        <CheckCircle2 className="h-4 w-4" />
                        Validierung
                    </TabsTrigger>
                    <TabsTrigger value="formate" className="flex items-center gap-2">
                        <FileCode className="h-4 w-4" />
                        Formate
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="uebersicht" className="space-y-6 mt-6">
                    <OverviewTab />
                </TabsContent>

                <TabsContent value="validierung" className="space-y-6 mt-6">
                    <ValidationTab />
                </TabsContent>

                <TabsContent value="formate" className="space-y-6 mt-6">
                    <FormatsTab />
                </TabsContent>
            </Tabs>
        </div>
    );
}

// =============================================================================
// OVERVIEW TAB
// =============================================================================

function OverviewTab() {
    const {
        data: mustangHealth,
        isLoading: isHealthLoading,
        refetch: refetchHealth,
    } = useMustangHealth();
    const {
        data: formatsData,
        isLoading: isFormatsLoading,
    } = useEInvoiceFormats();

    return (
        <>
            {/* KPI Cards */}
            <div className="grid gap-4 md:grid-cols-3">
                {/* Mustang Status */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            Mustang Service
                        </CardTitle>
                        <Heart className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {isHealthLoading ? (
                            <div className="space-y-2">
                                <Skeleton className="h-7 w-24" />
                                <Skeleton className="h-4 w-32" />
                            </div>
                        ) : (
                            <>
                                <div className="flex items-center gap-2">
                                    {mustangHealth?.available ? (
                                        <Badge className="bg-green-600 text-white">
                                            <CheckCircle2 className="h-3 w-3 mr-1" />
                                            Online
                                        </Badge>
                                    ) : (
                                        <Badge variant="destructive">
                                            <XCircle className="h-3 w-3 mr-1" />
                                            Offline
                                        </Badge>
                                    )}
                                </div>
                                <p className="text-xs text-muted-foreground mt-2">
                                    {mustangHealth?.available
                                        ? `Version: ${mustangHealth.mustangVersion || "Unbekannt"}`
                                        : mustangHealth?.error || "Service nicht erreichbar"}
                                </p>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="mt-2 h-7 text-xs px-2"
                                    onClick={() => refetchHealth()}
                                >
                                    <RefreshCw className="h-3 w-3 mr-1" />
                                    Aktualisieren
                                </Button>
                            </>
                        )}
                    </CardContent>
                </Card>

                {/* Supported Formats */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            Unterstuetzte Formate
                        </CardTitle>
                        <FileCode className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {isFormatsLoading ? (
                            <div className="space-y-2">
                                <Skeleton className="h-7 w-12" />
                                <Skeleton className="h-4 w-40" />
                            </div>
                        ) : (
                            <>
                                <div className="text-2xl font-bold">
                                    {formatsData?.formats?.length ?? 0}
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    Standard: {formatsData?.defaultFormat || "ZUGFeRD"}{" "}
                                    / {formatsData?.defaultProfile || "EN16931"}
                                </p>
                            </>
                        )}
                    </CardContent>
                </Card>

                {/* Features */}
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            Verfuegbare Features
                        </CardTitle>
                        <Shield className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        {isHealthLoading ? (
                            <div className="space-y-2">
                                <Skeleton className="h-4 w-full" />
                                <Skeleton className="h-4 w-3/4" />
                                <Skeleton className="h-4 w-1/2" />
                            </div>
                        ) : (
                            <div className="space-y-1">
                                <FeatureLine
                                    label="XRechnung UBL"
                                    available={mustangHealth?.features?.xrechnungUbl}
                                />
                                <FeatureLine
                                    label="KoSIT-Validierung"
                                    available={mustangHealth?.features?.kositValidation}
                                />
                                <FeatureLine
                                    label="PDF-Extraktion"
                                    available={mustangHealth?.features?.pdfExtraction}
                                />
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Quick Actions */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Schnellaktionen</CardTitle>
                    <CardDescription>
                        Haeufig verwendete E-Rechnungsfunktionen
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        <QuickActionCard
                            icon={Upload}
                            title="E-Rechnung validieren"
                            description="XML- oder PDF-Datei pruefen"
                            onClick={() => {
                                // Switch to validation tab
                                const tabTrigger = document.querySelector<HTMLButtonElement>(
                                    '[data-state][value="validierung"]'
                                );
                                tabTrigger?.click();
                            }}
                        />
                        <QuickActionCard
                            icon={FileText}
                            title="Formate anzeigen"
                            description="Unterstuetzte Standards und Profile"
                            onClick={() => {
                                const tabTrigger = document.querySelector<HTMLButtonElement>(
                                    '[data-state][value="formate"]'
                                );
                                tabTrigger?.click();
                            }}
                        />
                        <QuickActionCard
                            icon={ExternalLink}
                            title="XRechnung-Portal"
                            description="Offizielle E-Rechnungsplattform"
                            onClick={() => {
                                window.open(
                                    "https://www.e-rechnung-bund.de/",
                                    "_blank",
                                    "noopener,noreferrer"
                                );
                            }}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Info Section */}
            <div className="grid gap-4 md:grid-cols-2">
                <Alert>
                    <Info className="h-4 w-4" />
                    <AlertTitle>XRechnung 3.0</AlertTitle>
                    <AlertDescription className="space-y-2">
                        <p>
                            XRechnung ist der deutsche Standard fuer elektronische Rechnungen
                            an oeffentliche Auftraggeber (B2G). Seit dem 27.11.2020 ist
                            E-Invoicing fuer Lieferanten der Bundesverwaltung Pflicht.
                        </p>
                        <ul className="text-sm list-disc ml-4 space-y-1">
                            <li>Basiert auf EN 16931</li>
                            <li>Unterstuetzt CII und UBL 2.1 Syntax</li>
                            <li>Erfordert Leitweg-ID (BT-10)</li>
                            <li>Validierung ueber KoSIT-Prueftool</li>
                        </ul>
                        <a
                            href="https://www.xoev.de/xrechnung"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-sm text-primary hover:underline mt-2"
                        >
                            <ExternalLink className="h-3 w-3" />
                            Mehr erfahren
                        </a>
                    </AlertDescription>
                </Alert>

                <Alert>
                    <Info className="h-4 w-4" />
                    <AlertTitle>ZUGFeRD 2.x</AlertTitle>
                    <AlertDescription className="space-y-2">
                        <p>
                            ZUGFeRD (Zentraler User Guide des Forums elektronische Rechnung
                            Deutschland) kombiniert ein PDF/A-3 Dokument mit eingebettetem
                            XML. Ideal fuer den B2B-Austausch.
                        </p>
                        <ul className="text-sm list-disc ml-4 space-y-1">
                            <li>PDF mit eingebettetem XML (Factur-X)</li>
                            <li>5 Profile: Minimum bis Extended</li>
                            <li>Kompatibel mit EN 16931</li>
                            <li>Hybrides Format: Mensch + Maschine lesbar</li>
                        </ul>
                        <a
                            href="https://www.ferd-net.de/"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-sm text-primary hover:underline mt-2"
                        >
                            <ExternalLink className="h-3 w-3" />
                            Mehr erfahren
                        </a>
                    </AlertDescription>
                </Alert>
            </div>
        </>
    );
}

// =============================================================================
// VALIDATION TAB
// =============================================================================

function ValidationTab() {
    return (
        <div className="max-w-2xl">
            <EInvoiceValidator />
        </div>
    );
}

// =============================================================================
// FORMATS TAB
// =============================================================================

function FormatsTab() {
    const {
        data: formatsData,
        isLoading,
        error,
    } = useEInvoiceFormats();
    const {
        data: mustangHealth,
        isLoading: isHealthLoading,
    } = useMustangHealth();

    if (isLoading) {
        return (
            <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                    <Card key={i}>
                        <CardHeader>
                            <Skeleton className="h-5 w-48" />
                            <Skeleton className="h-4 w-full" />
                        </CardHeader>
                        <CardContent>
                            <div className="flex flex-wrap gap-2">
                                <Skeleton className="h-6 w-20" />
                                <Skeleton className="h-6 w-24" />
                                <Skeleton className="h-6 w-16" />
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>
        );
    }

    if (error) {
        return (
            <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Fehler</AlertTitle>
                <AlertDescription>
                    Formate konnten nicht geladen werden. Bitte versuchen Sie es spaeter erneut.
                </AlertDescription>
            </Alert>
        );
    }

    const formats = formatsData?.formats ?? [];

    return (
        <div className="space-y-6">
            {/* Mustang Health Status */}
            <MustangServiceCard
                health={mustangHealth}
                isLoading={isHealthLoading}
            />

            <Separator />

            {/* Profiles Overview */}
            <div>
                <h3 className="text-lg font-semibold mb-4">Profile</h3>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {(Object.entries(PROFILE_LABELS) as Array<[ZUGFeRDProfile, string]>).map(
                        ([key, label]) => (
                            <ProfileCard
                                key={key}
                                profileKey={key}
                                label={label}
                                isDefault={key === formatsData?.defaultProfile}
                            />
                        )
                    )}
                </div>
            </div>

            <Separator />

            {/* Supported Formats List */}
            <div>
                <h3 className="text-lg font-semibold mb-4">
                    Unterstuetzte Formate
                    {formats.length > 0 && (
                        <Badge variant="secondary" className="ml-2 text-xs">
                            {formats.length}
                        </Badge>
                    )}
                </h3>
                {formats.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                        Keine Formate verfuegbar. Pruefen Sie die Backend-Konfiguration.
                    </p>
                ) : (
                    <div className="space-y-3">
                        {formats.map((format) => (
                            <FormatCard key={format.id} format={format} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// =============================================================================
// HELPER COMPONENTS
// =============================================================================

function FeatureLine({
    label,
    available,
}: {
    label: string;
    available?: boolean;
}) {
    return (
        <div className="flex items-center gap-2 text-sm">
            {available ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
            ) : (
                <XCircle className="h-3.5 w-3.5 text-muted-foreground" />
            )}
            <span className={cn(!available && "text-muted-foreground")}>
                {label}
            </span>
        </div>
    );
}

function QuickActionCard({
    icon: Icon,
    title,
    description,
    onClick,
}: {
    icon: React.ElementType;
    title: string;
    description: string;
    onClick: () => void;
}) {
    return (
        <button
            onClick={onClick}
            className="flex items-start gap-3 p-4 rounded-lg border bg-card text-card-foreground hover:bg-accent hover:text-accent-foreground transition-colors text-left"
        >
            <Icon className="h-5 w-5 text-primary mt-0.5 shrink-0" />
            <div>
                <p className="text-sm font-medium">{title}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                    {description}
                </p>
            </div>
        </button>
    );
}

function MustangServiceCard({
    health,
    isLoading,
}: {
    health?: {
        status: string;
        available: boolean;
        mustangVersion?: string;
        javaVersion?: string;
        features?: {
            xrechnungUbl: boolean;
            kositValidation: boolean;
            pdfExtraction: boolean;
        };
        error?: string;
    };
    isLoading: boolean;
}) {
    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-5 w-40" />
                </CardHeader>
                <CardContent>
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-3/4 mt-2" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base">
                        Mustang Service Status
                    </CardTitle>
                    {health?.available ? (
                        <Badge className="bg-green-600 text-white">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Verfuegbar
                        </Badge>
                    ) : (
                        <Badge variant="destructive">
                            <XCircle className="h-3 w-3 mr-1" />
                            Nicht verfuegbar
                        </Badge>
                    )}
                </div>
            </CardHeader>
            <CardContent>
                {health?.available ? (
                    <div className="grid gap-2 sm:grid-cols-2 text-sm">
                        <div>
                            <span className="text-muted-foreground">
                                Mustang-Version:{" "}
                            </span>
                            <span className="font-medium">
                                {health.mustangVersion || "Unbekannt"}
                            </span>
                        </div>
                        {health.javaVersion && (
                            <div>
                                <span className="text-muted-foreground">
                                    Java-Version:{" "}
                                </span>
                                <span className="font-medium">
                                    {health.javaVersion}
                                </span>
                            </div>
                        )}
                        <div className="sm:col-span-2 flex flex-wrap gap-2 mt-1">
                            {health.features?.xrechnungUbl && (
                                <Badge variant="outline" className="text-xs">
                                    XRechnung UBL
                                </Badge>
                            )}
                            {health.features?.kositValidation && (
                                <Badge variant="outline" className="text-xs">
                                    KoSIT-Validierung
                                </Badge>
                            )}
                            {health.features?.pdfExtraction && (
                                <Badge variant="outline" className="text-xs">
                                    PDF-Extraktion
                                </Badge>
                            )}
                        </div>
                    </div>
                ) : (
                    <p className="text-sm text-muted-foreground">
                        {health?.error ||
                            "Der Mustang-Service ist nicht erreichbar. UBL-Generierung und KoSIT-Validierung sind nicht verfuegbar."}
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

function ProfileCard({
    profileKey,
    label,
    isDefault,
}: {
    profileKey: ZUGFeRDProfile;
    label: string;
    isDefault: boolean;
}) {
    const descriptions: Record<ZUGFeRDProfile, string> = {
        MINIMUM: "Mindestangaben fuer automatische Zuordnung",
        BASIC: "Grundlegende Rechnungsdaten",
        BASIC_WL: "Grunddaten ohne Einzelpositionen",
        EN16931: "Europaeische Norm (vollstaendig)",
        EXTENDED: "Erweitert mit zusaetzlichen Feldern",
        XRECHNUNG: "Fuer oeffentliche Auftraggeber (B2G)",
    };

    const b2gProfiles: ZUGFeRDProfile[] = ["EN16931", "XRECHNUNG"];
    const isB2G = b2gProfiles.includes(profileKey);

    return (
        <Card className={cn(isDefault && "border-primary")}>
            <CardContent className="pt-4">
                <div className="flex items-start justify-between">
                    <div>
                        <p className="text-sm font-medium">{label}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            {descriptions[profileKey]}
                        </p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                        {isDefault && (
                            <Badge variant="default" className="text-xs">
                                Standard
                            </Badge>
                        )}
                        {isB2G && (
                            <Badge
                                variant="secondary"
                                className="text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                            >
                                B2G
                            </Badge>
                        )}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

function FormatCard({ format }: { format: SupportedFormat }) {
    return (
        <Card>
            <CardContent className="pt-4">
                <div className="flex items-start justify-between">
                    <div className="space-y-1">
                        <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-primary" />
                            <span className="text-sm font-medium">
                                {format.name}
                            </span>
                            {format.b2gCompatible && (
                                <Badge
                                    variant="secondary"
                                    className="text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                                >
                                    B2G-kompatibel
                                </Badge>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {format.description}
                        </p>
                    </div>
                </div>
                {format.supportedProfiles.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-3">
                        {format.supportedProfiles.map((profile) => (
                            <Badge
                                key={profile}
                                variant="outline"
                                className="text-xs"
                            >
                                {PROFILE_LABELS[profile as ZUGFeRDProfile] || profile}
                            </Badge>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
