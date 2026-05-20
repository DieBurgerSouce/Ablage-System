/**
 * LineItemsTable - Zeigt Positionen einer Rechnung/Bestellung.
 */

import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { List } from "lucide-react";
import { formatCurrency } from "./CopyableField";
import type { ExtractedLineItem } from "../types/extracted-data.types";

interface LineItemsTableProps {
    items: ExtractedLineItem[];
    currency?: string;
    className?: string;
}

export function LineItemsTable({
    items,
    currency = "EUR",
    className,
}: LineItemsTableProps) {
    if (!items || items.length === 0) {
        return null;
    }

    // Summe berechnen
    const total = items.reduce(
        (sum, item) => sum + (item.total_price || 0),
        0
    );

    return (
        <Card className={className}>
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <List className="h-4 w-4" />
                    Positionen ({items.length})
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="rounded-md border overflow-hidden">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="w-12">Pos</TableHead>
                                {items.some((i) => i.article_number) && (
                                    <TableHead className="w-24">Art-Nr.</TableHead>
                                )}
                                <TableHead>Beschreibung</TableHead>
                                <TableHead className="text-right w-16">Menge</TableHead>
                                {items.some((i) => i.unit) && (
                                    <TableHead className="w-16">Einheit</TableHead>
                                )}
                                <TableHead className="text-right w-24">E-Preis</TableHead>
                                <TableHead className="text-right w-24">Gesamt</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {items.map((item, index) => (
                                <TableRow key={item.position || index}>
                                    <TableCell className="font-medium">
                                        {item.position || index + 1}
                                    </TableCell>
                                    {items.some((i) => i.article_number) && (
                                        <TableCell className="font-mono text-xs">
                                            {item.article_number || "-"}
                                        </TableCell>
                                    )}
                                    <TableCell className="max-w-xs truncate">
                                        {item.description || "-"}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        {item.quantity?.toLocaleString("de-DE") || "-"}
                                    </TableCell>
                                    {items.some((i) => i.unit) && (
                                        <TableCell>{item.unit || "-"}</TableCell>
                                    )}
                                    <TableCell className="text-right">
                                        {item.unit_price != null
                                            ? formatCurrency(item.unit_price, currency)
                                            : "-"}
                                    </TableCell>
                                    <TableCell className="text-right font-medium">
                                        {item.total_price != null
                                            ? formatCurrency(item.total_price, currency)
                                            : "-"}
                                    </TableCell>
                                </TableRow>
                            ))}
                            {/* Summenzeile */}
                            <TableRow className="bg-muted/50">
                                <TableCell
                                    colSpan={
                                        3 +
                                        (items.some((i) => i.article_number) ? 1 : 0) +
                                        (items.some((i) => i.unit) ? 1 : 0)
                                    }
                                    className="text-right font-medium"
                                >
                                    Summe Positionen:
                                </TableCell>
                                <TableCell className="text-right font-bold">
                                    {formatCurrency(total, currency)}
                                </TableCell>
                            </TableRow>
                        </TableBody>
                    </Table>
                </div>
            </CardContent>
        </Card>
    );
}
