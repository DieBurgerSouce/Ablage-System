import { useState } from "react";
import { Layers, MessageSquare, ChevronDown } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import type { BoundingBox, AnnotationTask } from "../types/annotations-extended-types";
import { CommentTaskBadge } from "./CommentTaskBadge";

interface AnnotationSidebarProps {
  boxes: BoundingBox[];
  tasks?: AnnotationTask[];
  selectedBoxId?: number;
  onBoxClick?: (boxId: number) => void;
  onTaskClick?: (taskId: number) => void;
}

interface GroupedBoxes {
  [page: number]: BoundingBox[];
}

export function AnnotationSidebar({
  boxes,
  tasks = [],
  selectedBoxId,
  onBoxClick,
  onTaskClick,
}: AnnotationSidebarProps) {
  const [expandedPages, setExpandedPages] = useState<Set<number>>(new Set([1]));

  // Group boxes by page
  const groupedBoxes = boxes.reduce<GroupedBoxes>((acc, box) => {
    if (!acc[box.page]) {
      acc[box.page] = [];
    }
    acc[box.page].push(box);
    return acc;
  }, {});

  const pages = Object.keys(groupedBoxes)
    .map(Number)
    .sort((a, b) => a - b);

  const togglePage = (page: number) => {
    setExpandedPages((prev) => {
      const next = new Set(prev);
      if (next.has(page)) {
        next.delete(page);
      } else {
        next.add(page);
      }
      return next;
    });
  };

  // Find task for a box's comment
  const getTaskForBox = (box: BoundingBox): AnnotationTask | undefined => {
    // Assuming box.comment contains comment_id in some way
    // In real implementation, you'd need to link via comment_id
    return tasks.find((task) => task.commentId === box.id);
  };

  const formatDate = (date: Date) => {
    return new Intl.DateTimeFormat("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  };

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Layers className="w-5 h-5" />
          Annotationen
          <Badge variant="secondary" className="ml-auto">
            {boxes.length}
          </Badge>
        </CardTitle>
      </CardHeader>

      <Separator />

      <CardContent className="flex-1 p-0">
        <ScrollArea className="h-full">
          <div className="p-4 space-y-2">
            {pages.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">
                <Layers className="w-8 h-8 mx-auto mb-2 opacity-50" />
                Keine Annotationen vorhanden
              </div>
            ) : (
              pages.map((page) => {
                const pageBoxes = groupedBoxes[page];
                const isExpanded = expandedPages.has(page);

                return (
                  <div key={page} className="space-y-1">
                    {/* Page Header */}
                    <Button
                      variant="ghost"
                      className="w-full justify-start px-2 py-1 h-auto"
                      onClick={() => togglePage(page)}
                    >
                      <ChevronDown
                        className={`w-4 h-4 mr-2 transition-transform ${
                          isExpanded ? "" : "-rotate-90"
                        }`}
                      />
                      <span className="font-medium">Seite {page}</span>
                      <Badge variant="secondary" className="ml-auto">
                        {pageBoxes.length}
                      </Badge>
                    </Button>

                    {/* Page Boxes */}
                    {isExpanded && (
                      <div className="ml-4 space-y-1">
                        {pageBoxes.map((box) => {
                          const isSelected = box.id === selectedBoxId;
                          const task = getTaskForBox(box);

                          return (
                            <button
                              key={box.id}
                              className={`w-full text-left p-2 rounded-md border transition-colors ${
                                isSelected
                                  ? "bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700"
                                  : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-750"
                              }`}
                              onClick={() => onBoxClick?.(box.id)}
                            >
                              {/* Label with Color */}
                              <div className="flex items-center gap-2 mb-1">
                                <div
                                  className="w-3 h-3 rounded"
                                  style={{ backgroundColor: box.color }}
                                />
                                <span className="font-medium text-sm">
                                  {box.label}
                                </span>
                              </div>

                              {/* Comment Preview */}
                              {box.comment && (
                                <div className="flex items-start gap-1 text-xs text-muted-foreground mb-2">
                                  <MessageSquare className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                  <p className="line-clamp-2">{box.comment}</p>
                                </div>
                              )}

                              {/* Task Badge */}
                              {task && (
                                <div className="mt-2">
                                  <CommentTaskBadge
                                    task={task}
                                    onClick={() => onTaskClick?.(task.id)}
                                  />
                                </div>
                              )}

                              {/* Timestamp */}
                              <div className="text-xs text-muted-foreground mt-1">
                                {formatDate(box.createdAt)}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
