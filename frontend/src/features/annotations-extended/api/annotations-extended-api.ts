import { apiClient } from "@/lib/api/client";
import type {
  BoundingBoxBackend,
  CommentReplyBackend,
  AnnotationTaskBackend,
  CreateBoundingBoxRequest,
  CreateReplyRequest,
  CreateTaskRequest,
  UpdateTaskRequest,
  BoundingBox,
  CommentReply,
  AnnotationTask,
} from "../types/annotations-extended-types";
// Transformer sind Laufzeit-Funktionen -> kein import type
import {
  transformBoundingBox,
  transformCommentReply,
  transformAnnotationTask,
} from "../types/annotations-extended-types";

// Bounding Box Annotations

export const createBoundingBox = async (
  data: CreateBoundingBoxRequest
): Promise<BoundingBox> => {
  try {
    const response = await apiClient.post<BoundingBoxBackend>(
      "/annotations/bounding-box",
      data
    );
    return transformBoundingBox(response.data);
  } catch (error) {
    throw new Error("Fehler beim Erstellen der Bounding-Box-Annotation");
  }
};

export const getBoundingBoxes = async (
  documentId: number,
  page?: number
): Promise<BoundingBox[]> => {
  try {
    const response = await apiClient.get<BoundingBoxBackend[]>(
      `/annotations/bounding-box/${documentId}`,
      { params: page !== undefined ? { page } : undefined }
    );
    return response.data.map(transformBoundingBox);
  } catch (error) {
    throw new Error("Fehler beim Laden der Bounding-Box-Annotationen");
  }
};

// Comment Replies

export const createReply = async (
  data: CreateReplyRequest
): Promise<CommentReply> => {
  try {
    const response = await apiClient.post<CommentReplyBackend>(
      "/annotations/replies",
      data
    );
    return transformCommentReply(response.data);
  } catch (error) {
    throw new Error("Fehler beim Erstellen der Antwort");
  }
};

export const getReplies = async (commentId: number): Promise<CommentReply[]> => {
  try {
    const response = await apiClient.get<CommentReplyBackend[]>(
      `/annotations/replies/${commentId}`
    );
    return response.data.map(transformCommentReply);
  } catch (error) {
    throw new Error("Fehler beim Laden der Antworten");
  }
};

// Annotation Tasks

export const createTask = async (
  data: CreateTaskRequest
): Promise<AnnotationTask> => {
  try {
    const response = await apiClient.post<AnnotationTaskBackend>(
      "/annotations/tasks",
      data
    );
    return transformAnnotationTask(response.data);
  } catch (error) {
    throw new Error("Fehler beim Erstellen der Aufgabe");
  }
};

export interface GetTasksParams {
  status?: string;
  assignee_id?: number;
  document_id?: number;
}

export const getTasks = async (
  params?: GetTasksParams
): Promise<AnnotationTask[]> => {
  try {
    const response = await apiClient.get<AnnotationTaskBackend[]>(
      "/annotations/tasks",
      { params }
    );
    return response.data.map(transformAnnotationTask);
  } catch (error) {
    throw new Error("Fehler beim Laden der Aufgaben");
  }
};

export const updateTask = async (
  taskId: number,
  data: UpdateTaskRequest
): Promise<AnnotationTask> => {
  try {
    const response = await apiClient.patch<AnnotationTaskBackend>(
      `/annotations/tasks/${taskId}`,
      data
    );
    return transformAnnotationTask(response.data);
  } catch (error) {
    throw new Error("Fehler beim Aktualisieren der Aufgabe");
  }
};

export const deleteTask = async (taskId: number): Promise<void> => {
  try {
    await apiClient.delete(`/annotations/tasks/${taskId}`);
  } catch (error) {
    throw new Error("Fehler beim Löschen der Aufgabe");
  }
};
