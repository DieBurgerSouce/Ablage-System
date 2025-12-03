import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Layers, ChevronRight, Calendar, FileText } from "lucide-react"
import { Link } from "@tanstack/react-router"

// Mock data
const MOCK_GROUPS = [
    {
        id: "1",
        name: "Versicherungsunterlagen 2023",
        documentCount: 5,
        createdAt: "2023-11-15",
        status: "completed"
    },
    {
        id: "2",
        name: "Steuererklärung 2022",
        documentCount: 12,
        createdAt: "2023-10-01",
        status: "in_progress"
    },
    {
        id: "3",
        name: "Fahrzeugkauf Audi A4",
        documentCount: 3,
        createdAt: "2023-12-01",
        status: "completed"
    }
]

export function DocumentGroupList() {
    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold tracking-tight">Aktuelle Gruppen</h2>
                <Button variant="outline" size="sm">
                    Alle anzeigen
                </Button>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {MOCK_GROUPS.map((group) => (
                    <Card key={group.id} className="hover:bg-muted/50 transition-colors cursor-pointer group">
                        <Link to="/document-groups/$id" params={{ id: group.id }} className="block h-full">
                            <CardHeader className="pb-2">
                                <div className="flex justify-between items-start">
                                    <div className="p-2 bg-primary/10 rounded-lg">
                                        <Layers className="w-5 h-5 text-primary" />
                                    </div>
                                    <Badge variant={group.status === 'completed' ? 'secondary' : 'default'}>
                                        {group.status === 'completed' ? 'Fertig' : 'In Bearbeitung'}
                                    </Badge>
                                </div>
                                <CardTitle className="text-base mt-2 group-hover:text-primary transition-colors">
                                    {group.name}
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                                    <div className="flex items-center gap-1">
                                        <FileText className="w-4 h-4" />
                                        {group.documentCount} Dok.
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <Calendar className="w-4 h-4" />
                                        {new Date(group.createdAt).toLocaleDateString()}
                                    </div>
                                </div>
                            </CardContent>
                        </Link>
                    </Card>
                ))}
            </div>
        </div>
    )
}
