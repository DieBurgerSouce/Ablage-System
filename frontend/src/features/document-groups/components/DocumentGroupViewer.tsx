import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { FileText, Download, Trash2, ChevronLeft, Inbox } from "lucide-react"
import { Link } from "@tanstack/react-router"
import { useDocumentGroup } from "../hooks/use-document-groups"

export function DocumentGroupViewer({ groupId }: { groupId: string }) {
    const { data: group, isLoading } = useDocumentGroup(groupId)

    if (isLoading) {
        return (
            <div className="space-y-6">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Skeleton className="h-10 w-10 rounded-md" />
                        <div>
                            <Skeleton className="h-8 w-64 mb-2" />
                            <Skeleton className="h-4 w-48" />
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <Skeleton className="h-10 w-40" />
                        <Skeleton className="h-10 w-10" />
                    </div>
                </div>
                <div className="grid gap-6 md:grid-cols-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <Card key={i} className="overflow-hidden">
                            <Skeleton className="aspect-[3/4] w-full" />
                            <CardContent className="p-4">
                                <Skeleton className="h-5 w-3/4 mb-2" />
                                <Skeleton className="h-4 w-16" />
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>
        )
    }

    if (!group) {
        return (
            <div className="space-y-6">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" asChild>
                        <Link to="/document-groups">
                            <ChevronLeft className="w-5 h-5" />
                        </Link>
                    </Button>
                    <h1 className="text-3xl font-bold tracking-tight">Gruppe nicht gefunden</h1>
                </div>
                <Card className="border-dashed">
                    <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                        <div className="p-4 bg-muted rounded-full mb-4">
                            <Inbox className="w-8 h-8" />
                        </div>
                        <p className="text-lg font-medium">Gruppe nicht gefunden</p>
                        <p className="text-sm mt-1">
                            Die angeforderte Gruppe existiert nicht oder wurde geloescht.
                        </p>
                    </CardContent>
                </Card>
            </div>
        )
    }

    // Build page items from group.totalPages
    const pages = Array.from({ length: group.totalPages }, (_, i) => ({
        id: `${group.id}-page-${i + 1}`,
        name: `${group.name}_Seite${i + 1}.pdf`,
        page: i + 1,
    }))

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
                        <h1 className="text-3xl font-bold tracking-tight">
                            Gruppe: {group.name}
                        </h1>
                        <p className="text-muted-foreground">
                            {group.totalPages} Seiten &bull; Erstellt am{' '}
                            {new Date(group.createdAt).toLocaleDateString('de-DE')}
                        </p>
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

            {pages.length === 0 ? (
                <Card className="border-dashed">
                    <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                        <div className="p-4 bg-muted rounded-full mb-4">
                            <Inbox className="w-8 h-8" />
                        </div>
                        <p className="text-lg font-medium">Keine Seiten vorhanden</p>
                        <p className="text-sm mt-1">
                            Diese Gruppe enthaelt noch keine Seiten.
                        </p>
                    </CardContent>
                </Card>
            ) : (
                <div className="grid gap-6 md:grid-cols-3">
                    {pages.map((doc) => (
                        <Card key={doc.id} className="overflow-hidden">
                            <div className="aspect-[3/4] bg-muted flex items-center justify-center border-b">
                                <FileText className="w-12 h-12 text-muted-foreground/50" />
                            </div>
                            <CardContent className="p-4">
                                <div className="font-medium truncate" title={doc.name}>
                                    {doc.name}
                                </div>
                                <div className="text-sm text-muted-foreground mt-1">
                                    Seite {doc.page}
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    )
}
