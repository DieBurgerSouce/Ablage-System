import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Check, X, ChevronLeft, Save, RotateCcw } from "lucide-react"
import { Link } from "@tanstack/react-router"
import { ConfidenceIndicator } from "./ConfidenceIndicator"

// Mock data for a single document's fields
const MOCK_FIELDS = [
    { key: "invoice_number", label: "Rechnungsnummer", value: "RE-2023-001", confidence: 0.95 },
    { key: "date", label: "Rechnungsdatum", value: "01.12.2023", confidence: 0.98 },
    { key: "total_amount", label: "Gesamtbetrag", value: "1.250,00 €", confidence: 0.85 },
    { key: "vendor", label: "Lieferant", value: "Muster GmbH", confidence: 0.99 },
    { key: "iban", label: "IBAN", value: "DE12 3456 7890 1234 5678 90", confidence: 0.60 }, // Low confidence
]

export function ValidationEditor({ documentId }: { documentId: string }) {
    const [fields, setFields] = useState(MOCK_FIELDS)

    const handleFieldChange = (index: number, newValue: string) => {
        const newFields = [...fields]
        newFields[index].value = newValue
        setFields(newFields)
    }

    return (
        <div className="h-[calc(100vh-4rem)] flex flex-col">
            {/* Header */}
            <div className="border-b bg-background p-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" asChild>
                        <Link to="/validation-queue">
                            <ChevronLeft className="w-5 h-5" />
                        </Link>
                    </Button>
                    <div>
                        <h2 className="text-lg font-semibold">Validierung: {documentId}</h2>
                        <p className="text-xs text-muted-foreground">Rechnung • 5 Felder zu prüfen</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" className="gap-2">
                        <RotateCcw className="w-4 h-4" />
                        Zurücksetzen
                    </Button>
                    <Button variant="destructive" className="gap-2">
                        <X className="w-4 h-4" />
                        Ablehnen
                    </Button>
                    <Button className="gap-2 bg-green-600 hover:bg-green-700">
                        <Check className="w-4 h-4" />
                        Bestätigen & Speichern
                    </Button>
                </div>
            </div>

            {/* Main Content - Split View */}
            <div className="flex-1 flex overflow-hidden">
                {/* Left: Document Viewer (Placeholder) */}
                <div className="w-1/2 bg-muted/30 border-r p-4 flex items-center justify-center">
                    <div className="text-center text-muted-foreground">
                        <div className="w-64 h-96 bg-white shadow-lg mx-auto mb-4 border flex items-center justify-center">
                            PDF Preview
                        </div>
                        <p>Dokument-Vorschau hier</p>
                    </div>
                </div>

                {/* Right: Fields Editor */}
                <div className="w-1/2 overflow-y-auto p-6 bg-background">
                    <Card>
                        <CardHeader>
                            <CardTitle>Extrahierte Daten</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            {fields.map((field, index) => (
                                <div key={field.key} className="space-y-2">
                                    <div className="flex justify-between items-center">
                                        <Label htmlFor={field.key}>{field.label}</Label>
                                        <ConfidenceIndicator score={field.confidence} />
                                    </div>
                                    <div className="flex gap-2">
                                        <Input
                                            id={field.key}
                                            value={field.value}
                                            onChange={(e) => handleFieldChange(index, e.target.value)}
                                            className={field.confidence < 0.8 ? "border-yellow-500 bg-yellow-500/5" : ""}
                                        />
                                        {field.confidence < 0.8 && (
                                            <Button size="icon" variant="ghost" title="Originalwert wiederherstellen">
                                                <RotateCcw className="w-4 h-4" />
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            ))}

                            <Separator className="my-6" />

                            <div className="bg-blue-50 text-blue-800 p-4 rounded-md text-sm">
                                <p className="font-semibold mb-1">Hinweis</p>
                                <p>Bitte überprüfen Sie besonders die gelb markierten Felder, da hier die Erkennungsrate niedrig war.</p>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    )
}
