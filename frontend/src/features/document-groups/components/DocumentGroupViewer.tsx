import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { FileText, Download, Trash2, ChevronLeft } from "lucide-react"
import { Link } from "@tanstack/react-router"

// Mock data
const MOCK_GROUP_DOCS = [
    { id: '1', name: 'Versicherungsschein_Seite1.pdf', page: 1 },
    { id: '2', name: 'Versicherungsschein_Seite2.pdf', page: 2 },
    { id: '3', name: 'Versicherungsschein_AGB.pdf', page: 3 },
]

export function DocumentGroupViewer({ groupId }: { groupId: string }) {
    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" asChild>
                        <Link to="/document-groups">
                            <ChevronLeft className="w-5 h-5" />
                        </Link>
                    </Button>
                    <div>
                        <h2 className="text-2xl font-bold tracking-tight">Gruppe: {groupId}</h2>
                        <p className="text-muted-foreground">3 Dokumente • Erstellt am 15.11.2023</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" className="gap-2">
                        <Download className="w-4 h-4" />
                        Als PDF exportieren
                    </Button>
                    <Button variant="destructive" size="icon">
                        <Trash2 className="w-4 h-4" />
                    </Button>
                </div>
            </div>

            <div className="grid gap-6 md:grid-cols-3">
                {MOCK_GROUP_DOCS.map((doc) => (
                    <Card key={doc.id} className="overflow-hidden">
                        <div className="aspect-[3/4] bg-muted flex items-center justify-center border-b">
                            <FileText className="w-12 h-12 text-muted-foreground/50" />
                        </div>
                        <CardContent className="p-4">
                            <div className="font-medium truncate" title={doc.name}>{doc.name}</div>
                            <div className="text-sm text-muted-foreground mt-1">Seite {doc.page}</div>
                        </CardContent>
                    </Card>
                ))}
            </div>
        </div>
    )
}
