/**
 * EInvoicePreview - XML Vorschau Komponente.
 *
 * Features:
 * - Syntax-Hervorhebung fuer XML
 * - Zeilennummern
 * - Kopieren-Button
 * - Download-Button
 * - Zusammenklappbar bei grossem XML
 */

import { useState, useMemo, useCallback } from "react";
import {
    Copy,
    Download,
    Check,
    ChevronDown,
    ChevronUp,
    FileCode,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface EInvoicePreviewProps {
    /** XML content to display */
    xmlContent: string;
    /** Optional filename for download */
    filename?: string;
    /** Maximum lines shown before collapsing */
    maxLines?: number;
    /** Optional additional className */
    className?: string;
}

/** Default max lines before content is collapsed */
const DEFAULT_MAX_LINES = 50;

export function EInvoicePreview({
    xmlContent,
    filename = "einvoice.xml",
    maxLines = DEFAULT_MAX_LINES,
    className,
}: EInvoicePreviewProps) {
    const [copied, setCopied] = useState(false);
    const [expanded, setExpanded] = useState(false);

    const lines = useMemo(() => xmlContent.split("\n"), [xmlContent]);
    const isLong = lines.length > maxLines;
    const displayedLines = isLong && !expanded ? lines.slice(0, maxLines) : lines;

    const handleCopy = useCallback(async () => {
        try {
            await navigator.clipboard.writeText(xmlContent);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Fallback fuer aeltere Browser
            const textarea = document.createElement("textarea");
            textarea.value = xmlContent;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            document.body.removeChild(textarea);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    }, [xmlContent]);

    const handleDownload = useCallback(() => {
        const blob = new Blob([xmlContent], { type: "application/xml" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }, [xmlContent, filename]);

    return (
        <Card className={className}>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <FileCode className="h-4 w-4" />
                        XML-Vorschau
                    </CardTitle>
                    <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="text-xs">
                            {lines.length} Zeilen
                        </Badge>
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 w-7 p-0"
                                        onClick={handleCopy}
                                    >
                                        {copied ? (
                                            <Check className="h-3.5 w-3.5 text-green-600" />
                                        ) : (
                                            <Copy className="h-3.5 w-3.5" />
                                        )}
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                    {copied ? "Kopiert" : "XML kopieren"}
                                </TooltipContent>
                            </Tooltip>

                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 w-7 p-0"
                                        onClick={handleDownload}
                                    >
                                        <Download className="h-3.5 w-3.5" />
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent>XML herunterladen</TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <div className="relative rounded-md border bg-muted/50 overflow-hidden">
                    <div className="overflow-x-auto">
                        <pre className="text-xs leading-5 p-0 m-0">
                            <code>
                                {displayedLines.map((line, idx) => (
                                    <div
                                        key={idx}
                                        className={cn(
                                            "flex hover:bg-muted/80 transition-colors",
                                            idx % 2 === 0
                                                ? "bg-transparent"
                                                : "bg-muted/30"
                                        )}
                                    >
                                        <span className="select-none text-muted-foreground text-right px-3 py-0.5 border-r border-border/50 min-w-[3rem] inline-block">
                                            {idx + 1}
                                        </span>
                                        <span className="px-3 py-0.5 whitespace-pre font-mono">
                                            <XmlHighlightedLine content={line} />
                                        </span>
                                    </div>
                                ))}
                            </code>
                        </pre>
                    </div>

                    {/* Collapse / Expand overlay */}
                    {isLong && (
                        <div
                            className={cn(
                                "flex justify-center py-2 border-t",
                                !expanded &&
                                    "bg-gradient-to-t from-background/90 to-transparent -mt-8 pt-10 relative"
                            )}
                        >
                            <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => setExpanded(!expanded)}
                                className="text-xs"
                            >
                                {expanded ? (
                                    <>
                                        <ChevronUp className="h-3 w-3 mr-1" />
                                        Weniger anzeigen
                                    </>
                                ) : (
                                    <>
                                        <ChevronDown className="h-3 w-3 mr-1" />
                                        Alle {lines.length} Zeilen anzeigen
                                    </>
                                )}
                            </Button>
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

/**
 * Simple XML syntax highlighting without external dependencies.
 * Highlights tags, attributes, values and comments.
 */
function XmlHighlightedLine({ content }: { content: string }) {
    const parts = useMemo(() => {
        const result: Array<{ text: string; type: "tag" | "attr" | "value" | "comment" | "text" }> = [];

        // Comment
        if (content.trim().startsWith("<!--")) {
            result.push({ text: content, type: "comment" });
            return result;
        }

        // Simple regex-based tokenizer
        let remaining = content;
        // Match XML tags, attributes, values
        const tokenRegex = /(<\/?[\w:.-]+)|(\s[\w:.-]+=)|("[^"]*")|('(?:[^']*)')|(\/>|>)/g;
        let lastIndex = 0;
        let match: RegExpExecArray | null;

        while ((match = tokenRegex.exec(remaining)) !== null) {
            // Text before match
            if (match.index > lastIndex) {
                result.push({
                    text: remaining.slice(lastIndex, match.index),
                    type: "text",
                });
            }

            if (match[1]) {
                // Tag name
                result.push({ text: match[1], type: "tag" });
            } else if (match[2]) {
                // Attribute name
                result.push({ text: match[2], type: "attr" });
            } else if (match[3] || match[4]) {
                // Attribute value (double or single quoted)
                result.push({ text: match[3] || match[4], type: "value" });
            } else if (match[5]) {
                // Closing bracket
                result.push({ text: match[5], type: "tag" });
            }

            lastIndex = match.index + match[0].length;
        }

        // Remaining text
        if (lastIndex < remaining.length) {
            result.push({
                text: remaining.slice(lastIndex),
                type: "text",
            });
        }

        return result;
    }, [content]);

    return (
        <>
            {parts.map((part, idx) => {
                const colorClass =
                    part.type === "tag"
                        ? "text-blue-600 dark:text-blue-400"
                        : part.type === "attr"
                          ? "text-orange-600 dark:text-orange-400"
                          : part.type === "value"
                            ? "text-green-600 dark:text-green-400"
                            : part.type === "comment"
                              ? "text-muted-foreground italic"
                              : "";

                return (
                    <span key={idx} className={colorClass}>
                        {part.text}
                    </span>
                );
            })}
        </>
    );
}
