import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Trash2, Link2, ArrowRightLeft, Copy, FileSymlink } from "lucide-react"
import type { DocumentRelationship } from "../types"
import { Badge } from "@/components/ui/badge"

interface RelationshipTableProps {
    relationships: DocumentRelationship[];
    onDelete: (id: string) => void;
}

const typeIcons: Record<string, any> = {
    related: Link2,
    parent: FileSymlink,
    child: FileSymlink,
    duplicate: Copy,
    reference: ArrowRightLeft
};

const typeColors: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    related: "secondary",
    parent: "default",
    child: "default",
    duplicate: "destructive",
    reference: "outline"
};

export function RelationshipTable({ relationships, onDelete }: RelationshipTableProps) {
    return (
        <div className="rounded-xl border bg-card text-card-foreground shadow-sm overflow-hidden">
            <Table>
                <TableHeader>
                    <TableRow className="bg-muted/50">
                        <TableHead>Quelle</TableHead>
                        <TableHead>Ziel</TableHead>
                        <TableHead>Beziehungstyp</TableHead>
                        <TableHead className="text-right">Aktionen</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {relationships.length === 0 ? (
                        <TableRow>
                            <TableCell colSpan={4} className="h-32 text-center text-muted-foreground">
                                Keine Beziehungen gefunden.
                            </TableCell>
                        </TableRow>
                    ) : (
                        relationships.map((rel) => {
                            const Icon = typeIcons[rel.type] || Link2;
                            return (
                                <TableRow key={rel.id} className="hover:bg-muted/50 transition-colors">
                                    <TableCell className="font-mono text-xs text-muted-foreground">
                                        {rel.sourceDocumentId.substring(0, 8)}...
                                    </TableCell>
                                    <TableCell className="font-mono text-xs text-muted-foreground">
                                        {rel.targetDocumentId.substring(0, 8)}...
                                    </TableCell>
                                    <TableCell>
                                        <Badge variant={typeColors[rel.type] || "secondary"} className="gap-1">
                                            <Icon className="w-3 h-3" />
                                            {rel.type}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => onDelete(rel.id)}
                                            className="hover:bg-destructive/10 hover:text-destructive"
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            );
                        })
                    )}
                </TableBody>
            </Table>
        </div>
    )
}
