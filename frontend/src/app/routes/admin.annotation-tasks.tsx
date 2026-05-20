import { createFileRoute } from "@tanstack/react-router";
import { AnnotationTasksPage } from "@/features/annotations-extended";

export const Route = createFileRoute("/admin/annotation-tasks")({
  component: AnnotationTasksPage,
});
