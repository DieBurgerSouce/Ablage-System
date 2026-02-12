/**
 * Papierkorb-Seite
 *
 * Zeigt gelöschte Dokumente mit Wiederherstellungsoption.
 * GDPR-konform mit 30-Tage-Frist.
 */

import { useState } from 'react'
import { Trash2, RotateCcw, AlertTriangle, Clock, FileText, Loader2 } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/use-toast'

import {
    useTrashList,
    useTrashStats,
    useRestoreDocument,
    usePermanentDelete,
    useEmptyTrash,
} from '../api'
import type { DeletedDocumentSummary } from '../types'

function StatsCards() {
    const { data: stats, isLoading } = useTrashStats()

    if (isLoading) {
        return (
            <div className="grid gap-4 md:grid-cols-3 mb-6">
                {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-24" />
                ))}
            </div>
        )
    }

    return (
        <div className="grid gap-4 md:grid-cols-3 mb-6">
            <Card>
                <CardHeader className="pb-2">
                    <CardDescription>Gesamt im Papierkorb</CardDescription>
                    <CardTitle className="text-2xl">{stats?.total_items ?? 0}</CardTitle>
                </CardHeader>
            </Card>
            <Card>
                <CardHeader className="pb-2">
                    <CardDescription>Wiederherstellbar</CardDescription>
                    <CardTitle className="text-2xl text-green-600">
                        {stats?.can_restore_count ?? 0}
                    </CardTitle>
                </CardHeader>
            </Card>
            <Card>
                <CardHeader className="pb-2">
                    <CardDescription>Laufen bald ab</CardDescription>
                    <CardTitle className="text-2xl text-orange-600">
                        {stats?.expiring_soon_count ?? 0}
                    </CardTitle>
                </CardHeader>
            </Card>
        </div>
    )
}

function TrashItem({
    item,
    onRestore,
    onDelete,
    isRestoring,
    isDeleting,
}: {
    item: DeletedDocumentSummary
    onRestore: (id: string) => void
    onDelete: (id: string) => void
    isRestoring: boolean
    isDeleting: boolean
}) {
    const daysLeft = item.days_until_permanent_deletion
    const isUrgent = daysLeft <= 7

    return (
        <TableRow>
            <TableCell>
                <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <span className="font-medium">{item.filename}</span>
                </div>
            </TableCell>
            <TableCell>
                <Badge variant="outline">{item.document_type}</Badge>
            </TableCell>
            <TableCell>
                {formatDistanceToNow(new Date(item.deleted_at), {
                    addSuffix: true,
                    locale: de,
                })}
            </TableCell>
            <TableCell>
                <div className="flex items-center gap-1">
                    <Clock className={`h-4 w-4 ${isUrgent ? 'text-orange-500' : 'text-muted-foreground'}`} />
                    <span className={isUrgent ? 'text-orange-600 font-medium' : ''}>
                        {daysLeft} {daysLeft === 1 ? 'Tag' : 'Tage'}
                    </span>
                </div>
            </TableCell>
            <TableCell>
                <div className="flex items-center gap-2">
                    {item.can_restore && (
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() => onRestore(item.id)}
                            disabled={isRestoring || isDeleting}
                        >
                            {isRestoring ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <RotateCcw className="h-4 w-4 mr-1" />
                            )}
                            Wiederherstellen
                        </Button>
                    )}
                    <AlertDialog>
                        <AlertDialogTrigger asChild>
                            <Button
                                size="sm"
                                variant="destructive"
                                disabled={isRestoring || isDeleting}
                            >
                                {isDeleting ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <Trash2 className="h-4 w-4 mr-1" />
                                )}
                                Löschen
                            </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                            <AlertDialogHeader>
                                <AlertDialogTitle>Dokument permanent löschen?</AlertDialogTitle>
                                <AlertDialogDescription>
                                    Diese Aktion kann nicht rückgängig gemacht werden. Das Dokument
                                    &quot;{item.filename}&quot; wird unwiderruflich gelöscht.
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                                <AlertDialogAction
                                    onClick={() => onDelete(item.id)}
                                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                >
                                    Permanent löschen
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                </div>
            </TableCell>
        </TableRow>
    )
}

export function TrashPage() {
    const { data: trashData, isLoading, error } = useTrashList()
    const restoreMutation = useRestoreDocument()
    const deleteMutation = usePermanentDelete()
    const emptyTrashMutation = useEmptyTrash()

    const [restoringId, setRestoringId] = useState<string | null>(null)
    const [deletingId, setDeletingId] = useState<string | null>(null)

    const handleRestore = async (id: string) => {
        setRestoringId(id)
        try {
            await restoreMutation.mutateAsync(id)
            toast({
                title: 'Dokument wiederhergestellt',
                description: 'Das Dokument wurde erfolgreich wiederhergestellt.',
            })
        } catch (err) {
            toast({
                title: 'Fehler',
                description: 'Das Dokument konnte nicht wiederhergestellt werden.',
                variant: 'destructive',
            })
        } finally {
            setRestoringId(null)
        }
    }

    const handleDelete = async (id: string) => {
        setDeletingId(id)
        try {
            await deleteMutation.mutateAsync(id)
            toast({
                title: 'Dokument gelöscht',
                description: 'Das Dokument wurde permanent gelöscht.',
            })
        } catch (err) {
            toast({
                title: 'Fehler',
                description: 'Das Dokument konnte nicht gelöscht werden.',
                variant: 'destructive',
            })
        } finally {
            setDeletingId(null)
        }
    }

    const handleEmptyTrash = async (onlyExpired: boolean) => {
        try {
            const result = await emptyTrashMutation.mutateAsync(onlyExpired)
            toast({
                title: 'Papierkorb geleert',
                description: result.message,
            })
        } catch (err) {
            toast({
                title: 'Fehler',
                description: 'Der Papierkorb konnte nicht geleert werden.',
                variant: 'destructive',
            })
        }
    }

    if (error) {
        return (
            <div className="container py-8">
                <Card className="border-destructive">
                    <CardHeader>
                        <CardTitle className="text-destructive">Fehler</CardTitle>
                        <CardDescription>
                            Der Papierkorb konnte nicht geladen werden.
                        </CardDescription>
                    </CardHeader>
                </Card>
            </div>
        )
    }

    return (
        <div className="container py-8 max-w-6xl">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-bold flex items-center gap-2">
                        <Trash2 className="h-8 w-8" />
                        Papierkorb
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Gelöschte Dokumente werden nach 30 Tagen permanent entfernt.
                    </p>
                </div>
                <div className="flex gap-2">
                    <AlertDialog>
                        <AlertDialogTrigger asChild>
                            <Button
                                variant="outline"
                                disabled={emptyTrashMutation.isPending || !trashData?.total}
                            >
                                Abgelaufene löschen
                            </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                            <AlertDialogHeader>
                                <AlertDialogTitle>Abgelaufene Dokumente löschen?</AlertDialogTitle>
                                <AlertDialogDescription>
                                    Alle Dokumente, deren 30-Tage-Frist abgelaufen ist, werden
                                    permanent gelöscht. Diese Aktion kann nicht rückgängig
                                    gemacht werden.
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                                <AlertDialogAction
                                    onClick={() => handleEmptyTrash(true)}
                                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                >
                                    Abgelaufene löschen
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>

                    <AlertDialog>
                        <AlertDialogTrigger asChild>
                            <Button
                                variant="destructive"
                                disabled={emptyTrashMutation.isPending || !trashData?.total}
                            >
                                {emptyTrashMutation.isPending && (
                                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                )}
                                Papierkorb leeren
                            </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                            <AlertDialogHeader>
                                <AlertDialogTitle className="flex items-center gap-2">
                                    <AlertTriangle className="h-5 w-5 text-destructive" />
                                    Papierkorb komplett leeren?
                                </AlertDialogTitle>
                                <AlertDialogDescription>
                                    <strong>Alle</strong> Dokumente im Papierkorb werden permanent
                                    gelöscht, auch solche, die noch wiederhergestellt werden
                                    könnten. Diese Aktion kann nicht rückgängig gemacht werden!
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                                <AlertDialogAction
                                    onClick={() => handleEmptyTrash(false)}
                                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                >
                                    Alles permanent löschen
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                </div>
            </div>

            <StatsCards />

            <Card>
                <CardHeader>
                    <CardTitle>Gelöschte Dokumente</CardTitle>
                    <CardDescription>
                        {trashData?.total ?? 0} Dokument{trashData?.total !== 1 ? 'e' : ''} im
                        Papierkorb
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {isLoading ? (
                        <div className="space-y-2">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-12 w-full" />
                            ))}
                        </div>
                    ) : trashData?.documents.length === 0 ? (
                        <div className="text-center py-12 text-muted-foreground">
                            <Trash2 className="h-12 w-12 mx-auto mb-4 opacity-30" />
                            <p>Der Papierkorb ist leer.</p>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Dateiname</TableHead>
                                    <TableHead>Typ</TableHead>
                                    <TableHead>Gelöscht</TableHead>
                                    <TableHead>Verbleibend</TableHead>
                                    <TableHead>Aktionen</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {trashData?.documents.map((item) => (
                                    <TrashItem
                                        key={item.id}
                                        item={item}
                                        onRestore={handleRestore}
                                        onDelete={handleDelete}
                                        isRestoring={restoringId === item.id}
                                        isDeleting={deletingId === item.id}
                                    />
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
