// Annotations Extended Types
// Backend API Types

export interface BoundingBoxBackend {
  id: number;
  document_id: number;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  color: string;
  comment?: string;
  created_by: number;
  created_at: string;
}

export interface CommentReplyBackend {
  id: number;
  comment_id: number;
  content: string;
  author: string;
  mentions: string[];
  created_at: string;
}

export type AnnotationTaskStatus = "offen" | "in_bearbeitung" | "erledigt" | "abgebrochen";
export type AnnotationTaskPriority = "niedrig" | "mittel" | "hoch" | "dringend";

export interface AnnotationTaskBackend {
  id: number;
  comment_id: number;
  title: string;
  assignee_id?: number;
  assignee?: string;
  status: AnnotationTaskStatus;
  priority: AnnotationTaskPriority;
  due_date?: string;
  created_at: string;
  updated_at?: string;
}

// Frontend Types

export interface BoundingBox {
  id: number;
  documentId: number;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  color: string;
  comment?: string;
  createdBy: number;
  createdAt: Date;
}

export interface CommentReply {
  id: number;
  commentId: number;
  content: string;
  author: string;
  mentions: string[];
  createdAt: Date;
}

export interface AnnotationTask {
  id: number;
  commentId: number;
  title: string;
  assigneeId?: number;
  assignee?: string;
  status: AnnotationTaskStatus;
  priority: AnnotationTaskPriority;
  dueDate?: Date;
  createdAt: Date;
  updatedAt?: Date;
}

// Transform Functions

export const transformBoundingBox = (backend: BoundingBoxBackend): BoundingBox => ({
  id: backend.id,
  documentId: backend.document_id,
  page: backend.page,
  x: backend.x,
  y: backend.y,
  width: backend.width,
  height: backend.height,
  label: backend.label,
  color: backend.color,
  comment: backend.comment,
  createdBy: backend.created_by,
  createdAt: new Date(backend.created_at),
});

export const transformCommentReply = (backend: CommentReplyBackend): CommentReply => ({
  id: backend.id,
  commentId: backend.comment_id,
  content: backend.content,
  author: backend.author,
  mentions: backend.mentions,
  createdAt: new Date(backend.created_at),
});

export const transformAnnotationTask = (backend: AnnotationTaskBackend): AnnotationTask => ({
  id: backend.id,
  commentId: backend.comment_id,
  title: backend.title,
  assigneeId: backend.assignee_id,
  assignee: backend.assignee,
  status: backend.status,
  priority: backend.priority,
  dueDate: backend.due_date ? new Date(backend.due_date) : undefined,
  createdAt: new Date(backend.created_at),
  updatedAt: backend.updated_at ? new Date(backend.updated_at) : undefined,
});

// Create Request Types

export interface CreateBoundingBoxRequest {
  document_id: number;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  color: string;
  comment?: string;
}

export interface CreateReplyRequest {
  comment_id: number;
  content: string;
  mentions?: string[];
}

export interface CreateTaskRequest {
  comment_id: number;
  title: string;
  assignee_id?: number;
  due_date?: string;
  priority: AnnotationTaskPriority;
}

export interface UpdateTaskRequest {
  status?: AnnotationTaskStatus;
  assignee_id?: number;
}

// UI Labels

export const TASK_STATUS_LABELS: Record<AnnotationTaskStatus, string> = {
  offen: "Offen",
  in_bearbeitung: "In Bearbeitung",
  erledigt: "Erledigt",
  abgebrochen: "Abgebrochen",
};

export const TASK_PRIORITY_LABELS: Record<AnnotationTaskPriority, string> = {
  niedrig: "Niedrig",
  mittel: "Mittel",
  hoch: "Hoch",
  dringend: "Dringend",
};

export const TASK_STATUS_COLORS: Record<AnnotationTaskStatus, string> = {
  offen: "bg-blue-100 text-blue-800",
  in_bearbeitung: "bg-yellow-100 text-yellow-800",
  erledigt: "bg-green-100 text-green-800",
  abgebrochen: "bg-gray-100 text-gray-800",
};

export const TASK_PRIORITY_COLORS: Record<AnnotationTaskPriority, string> = {
  niedrig: "bg-gray-100 text-gray-600",
  mittel: "bg-blue-100 text-blue-600",
  hoch: "bg-orange-100 text-orange-600",
  dringend: "bg-red-100 text-red-600",
};

export const DEFAULT_BOX_COLORS = [
  "#ef4444", // red
  "#f59e0b", // amber
  "#10b981", // green
  "#3b82f6", // blue
  "#8b5cf6", // purple
  "#ec4899", // pink
];
