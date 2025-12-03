import { ValidationCard } from "./ValidationCard"
import { CheckCircle, Clock, AlertTriangle, Filter } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

// Mock data
const MOCK_ITEMS = [
    {
        id: "1",
        documentName: "Rechnung_2023_001.pdf",
        documentType: "Rechnung",
        confidence: 0.85,
        status: "pending" as const,
        createdAt: "2023-12-01T10:00:00Z",
        fieldsToReview: 2
    },
    {
        id: "2",
        documentName: "Lieferschein_XYZ.pdf",
        documentType: "Lieferschein",
        confidence: 0.65,
        status: "pending" as const,
        createdAt: "2023-12-02T14:30:00Z",
        fieldsToReview: 4
    },
    {
        id: "3",
        documentName: "Vertrag_Entwurf.pdf",
        documentType: "Vertrag",
        confidence: 0.92,
        status: "pending" as const,
        createdAt: "2023-12-03T09:15:00Z",
        fieldsToReview: 1
    }
]

export function ValidationDashboard() {
    return (
        <div className="space-y-6">
            {/* Stats Overview */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-card p-4 rounded-lg border shadow-sm flex items-center gap-4">
                    <div className="p-3 bg-yellow-500/10 rounded-full">
                        <Clock className="w-6 h-6 text-yellow-600" />
                    </div>
                    <div>
                        <p className="text-sm text-muted-foreground">Ausstehend</p>
                        <h3 className="text-2xl font-bold">12</h3>
                    </div>
                </div>
                <div className="bg-card p-4 rounded-lg border shadow-sm flex items-center gap-4">
                    <div className="p-3 bg-green-500/10 rounded-full">
                        <CheckCircle className="w-6 h-6 text-green-600" />
                    </div>
                    <div>
                        <p className="text-sm text-muted-foreground">Heute geprüft</p>
                        <h3 className="text-2xl font-bold">45</h3>
                    </div>
                </div>
                <div className="bg-card p-4 rounded-lg border shadow-sm flex items-center gap-4">
                    <div className="p-3 bg-red-500/10 rounded-full">
                        <AlertTriangle className="w-6 h-6 text-red-600" />
                    </div>
                    <div>
                        <p className="text-sm text-muted-foreground">Kritische Fehler</p>
                        <h3 className="text-2xl font-bold">3</h3>
                    </div>
                </div>
            </div>

            {/* Filters */}
            <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
                <div className="flex items-center gap-2 w-full sm:w-auto">
                    <Input placeholder="Dokumente suchen..." className="w-full sm:w-[300px]" />
                    <Button variant="outline" size="icon">
                        <Filter className="w-4 h-4" />
                    </Button>
                </div>
                <div className="flex items-center gap-2 w-full sm:w-auto">
                    <Select defaultValue="all">
                        <SelectTrigger className="w-[180px]">
                            <SelectValue placeholder="Dokumenttyp" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Alle Typen</SelectItem>
                            <SelectItem value="invoice">Rechnungen</SelectItem>
                            <SelectItem value="delivery_note">Lieferscheine</SelectItem>
                            <SelectItem value="contract">Verträge</SelectItem>
                        </SelectContent>
                    </Select>
                    <Select defaultValue="priority">
                        <SelectTrigger className="w-[180px]">
                            <SelectValue placeholder="Sortierung" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="priority">Priorität</SelectItem>
                            <SelectItem value="date_desc">Neueste zuerst</SelectItem>
                            <SelectItem value="date_asc">Älteste zuerst</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>

            {/* Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {MOCK_ITEMS.map((item) => (
                    <ValidationCard key={item.id} item={item} />
                ))}
            </div>
        </div>
    )
}
