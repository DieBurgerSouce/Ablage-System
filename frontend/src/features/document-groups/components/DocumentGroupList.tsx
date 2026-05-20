import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Layers, Calendar, FileText, Inbox } from "lucide-react"
import { Link } from "@tanstack/react-router"
import { useDocumentGroups } from "../hooks/use-document-groups"

export function DocumentGroupList() {
    const { data: groups = [], isLoading } = useDocumentGroups()

    if (isLoading) {
        return (
            <div className="space-y-4">
                <div className="flex justify-between items-center">
                    <Skeleton className="h-7 w-48" />
                    <Skeleton className="h-9 w-28" />
                </div>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <Card key={i}>
                            <CardHeader className="pb-2">
                                <div className="flex justify-between items-start">
                                    <Skeleton className="h-9 w-9 rounded-lg" />
                                    <Skeleton className="h-5 w-24" />
                                </div>
                                <Skeleton className="h-5 w-3/4 mt-2" />
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-center gap-4">
                                    <Skeleton className="h-4 w-16" />
                                    <Skeleton className="h-4 w-24" />
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>
        )
    }

    if (groups.length === 0) {
        return (
            <div className="space-y-4">
                <div className="flex justify-between items-center">
                    <h2 className="text-xl font-semibold tracking-tight">Aktuelle Gruppen</h2>
                </div>
                <Card className="border-dashed">
                    <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                        <div className="p-4 bg-muted rounded-full mb-4">
                            <Inbox className="w-8 h-8" />
                        </div>
                        <p className="text-lg font-medium">Keine Gruppen vorhanden</p>
                        <p className="text-sm mt-1">
                            Erstellen Sie eine neue Dokumentgruppe, um zu beginnen.
                        </p>
                    </CardContent>
                </Card>
            </div>
        )
    }

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold tracking-tight">Aktuelle Gruppen</h2>
                <Button variant="outline" size="sm">
                    Alle anzeigen
                </Button>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {groups.map((group) => {
                    const status = group.userConfirmed ? 'completed' : 'in_progress'

                    return (
                        <Card key={group.id} className="hover:bg-muted/50 transition-colors cursor-pointer group">
                            <Link to="/document-groups/$id" params={{ id: group.id }} className="block h-full">
                                <CardHeader className="pb-2">
                                    <div className="flex justify-between items-start">
                                        <div className="p-2 bg-primary/10 rounded-lg">
                                            <Layers className="w-5 h-5 text-primary" />
                                        </div>
                                        <Badge variant={status === 'completed' ? 'secondary' : 'default'}>
                                            {status === 'completed' ? 'Fertig' : 'In Bearbeitung'}
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
                                            {group.totalPages} Seiten
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <Calendar className="w-4 h-4" />
                                            {new Date(group.createdAt).toLocaleDateString('de-DE')}
                                        </div>
                                    </div>
                                </CardContent>
                            </Link>
                        </Card>
                    )
                })}
            </div>
        </div>
    )
}
