import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Edit, Trash2, Building2, User } from "lucide-react"
import { Link } from "@tanstack/react-router"

// Mock data
const MOCK_ENTITIES = [
    {
        id: "1",
        name: "Muster GmbH",
        type: "company",
        taxId: "DE123456789",
        documentCount: 45,
        status: "active"
    },
    {
        id: "2",
        name: "Max Mustermann",
        type: "person",
        taxId: "-",
        documentCount: 12,
        status: "active"
    },
    {
        id: "3",
        name: "Versicherung AG",
        type: "company",
        taxId: "DE987654321",
        documentCount: 156,
        status: "active"
    }
]

export function BusinessEntityTable() {
    return (
        <div className="rounded-md border">
            <Table>
                <TableHeader>
                    <TableRow>
                        <TableHead className="w-[50px]"></TableHead>
                        <TableHead>Name</TableHead>
                        <TableHead>Typ</TableHead>
                        <TableHead>Steuer-ID</TableHead>
                        <TableHead>Dokumente</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Aktionen</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {MOCK_ENTITIES.map((entity) => (
                        <TableRow key={entity.id}>
                            <TableCell>
                                {entity.type === 'company' ? (
                                    <Building2 className="w-4 h-4 text-muted-foreground" />
                                ) : (
                                    <User className="w-4 h-4 text-muted-foreground" />
                                )}
                            </TableCell>
                            <TableCell className="font-medium">
                                <Link to="/business-entities/$id" params={{ id: entity.id }} className="hover:underline">
                                    {entity.name}
                                </Link>
                            </TableCell>
                            <TableCell>
                                {entity.type === 'company' ? 'Firma' : 'Privatperson'}
                            </TableCell>
                            <TableCell>{entity.taxId}</TableCell>
                            <TableCell>{entity.documentCount}</TableCell>
                            <TableCell>
                                <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                                    {entity.status}
                                </Badge>
                            </TableCell>
                            <TableCell className="text-right">
                                <div className="flex justify-end gap-2">
                                    <Button variant="ghost" size="icon">
                                        <Edit className="w-4 h-4" />
                                    </Button>
                                    <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive">
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                </div>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </div>
    )
}
