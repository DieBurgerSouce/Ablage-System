/**
 * GraphControls Component
 *
 * Steuerungsleiste für den Entity-Graph mit Filter-Optionen.
 */

import { Users, Truck, Filter, RefreshCw, Loader2, FileText, Maximize2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Slider } from '@/components/ui/slider';
import type { GraphStatistics } from '../api/relationships-api';

// ==================== Types ====================

interface GraphControlsProps {
    entityType: string;
    onEntityTypeChange: (value: string) => void;
    minDocuments: number;
    onMinDocumentsChange: (value: number) => void;
    includeDocuments: boolean;
    onIncludeDocumentsChange: (value: boolean) => void;
    limit: number;
    onLimitChange: (value: number) => void;
    statistics?: GraphStatistics;
    isLoading: boolean;
    isFetching: boolean;
    onRefresh: () => void;
    onFitView: () => void;
}

// ==================== Component ====================

export function GraphControls({
    entityType,
    onEntityTypeChange,
    minDocuments,
    onMinDocumentsChange,
    includeDocuments,
    onIncludeDocumentsChange,
    limit,
    onLimitChange,
    statistics,
    isLoading,
    isFetching,
    onRefresh,
    onFitView,
}: GraphControlsProps) {
    return (
        <Card className="mb-4">
            <CardContent className="py-4">
                <div className="flex flex-wrap items-center gap-6">
                    {/* Entity-Typ Filter */}
                    <div className="flex items-center gap-2">
                        <Filter className="h-4 w-4 text-muted-foreground" />
                        <Select value={entityType} onValueChange={onEntityTypeChange}>
                            <SelectTrigger className="w-[150px]">
                                <SelectValue placeholder="Alle Typen" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Alle Typen</SelectItem>
                                <SelectItem value="customer">
                                    <span className="flex items-center gap-2">
                                        <Users className="h-3.5 w-3.5" />
                                        Kunden
                                    </span>
                                </SelectItem>
                                <SelectItem value="supplier">
                                    <span className="flex items-center gap-2">
                                        <Truck className="h-3.5 w-3.5" />
                                        Lieferanten
                                    </span>
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Min. Dokumente Slider */}
                    <div className="flex items-center gap-3">
                        <Label className="text-sm text-muted-foreground whitespace-nowrap">
                            Min. Dokumente:
                        </Label>
                        <Slider
                            value={[minDocuments]}
                            onValueChange={([value]) => onMinDocumentsChange(value)}
                            min={0}
                            max={20}
                            step={1}
                            className="w-[120px]"
                        />
                        <Badge variant="secondary" className="w-8 justify-center">
                            {minDocuments}
                        </Badge>
                    </div>

                    {/* Limit Slider */}
                    <div className="flex items-center gap-3">
                        <Label className="text-sm text-muted-foreground whitespace-nowrap">
                            Max. Nodes:
                        </Label>
                        <Slider
                            value={[limit]}
                            onValueChange={([value]) => onLimitChange(value)}
                            min={10}
                            max={100}
                            step={10}
                            className="w-[100px]"
                        />
                        <Badge variant="secondary" className="w-10 justify-center">
                            {limit}
                        </Badge>
                    </div>

                    {/* Dokumente einbeziehen */}
                    <div className="flex items-center gap-2">
                        <Switch
                            id="include-docs"
                            checked={includeDocuments}
                            onCheckedChange={onIncludeDocumentsChange}
                        />
                        <Label htmlFor="include-docs" className="text-sm cursor-pointer">
                            <span className="flex items-center gap-1">
                                <FileText className="h-3.5 w-3.5" />
                                Dokumente
                            </span>
                        </Label>
                    </div>

                    {/* Spacer */}
                    <div className="flex-1" />

                    {/* Statistiken */}
                    {statistics && (
                        <div className="flex items-center gap-3 text-sm text-muted-foreground">
                            <Badge variant="outline" className="gap-1">
                                <Users className="h-3 w-3" />
                                {statistics.customerCount}
                            </Badge>
                            <Badge variant="outline" className="gap-1">
                                <Truck className="h-3 w-3" />
                                {statistics.supplierCount}
                            </Badge>
                            {statistics.documentNodes > 0 && (
                                <Badge variant="outline" className="gap-1">
                                    <FileText className="h-3 w-3" />
                                    {statistics.documentNodes}
                                </Badge>
                            )}
                        </div>
                    )}

                    {/* Aktionen */}
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onFitView}
                            title="Ansicht anpassen"
                        >
                            <Maximize2 className="h-4 w-4" />
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onRefresh}
                            disabled={isFetching}
                        >
                            {isFetching ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                <RefreshCw className="h-4 w-4" />
                            )}
                        </Button>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

export default GraphControls;
