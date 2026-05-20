import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type {
  BoundingBox,
  CommentReply,
  AnnotationTask,
  CreateBoundingBoxRequest,
  CreateReplyRequest,
  CreateTaskRequest,
  UpdateTaskRequest,
} from "../types/annotations-extended-types";
import {
  createBoundingBox,
  getBoundingBoxes,
  createReply,
  getReplies,
  createTask,
  getTasks,
  updateTask,
  deleteTask,
  type GetTasksParams,
} from "../api/annotations-extended-api";

// Query Keys

export const annotationKeys = {
  all: ["annotations"] as const,
  boundingBoxes: (documentId: number, page?: number) =>
    [...annotationKeys.all, "bounding-boxes", documentId, page] as const,
  replies: (commentId: number) =>
    [...annotationKeys.all, "replies", commentId] as const,
  tasks: (params?: GetTasksParams) =>
    [...annotationKeys.all, "tasks", params] as const,
};

// Bounding Box Queries

export const useBoundingBoxes = (documentId: number, page?: number) => {
  return useQuery({
    queryKey: annotationKeys.boundingBoxes(documentId, page),
    queryFn: () => getBoundingBoxes(documentId, page),
    enabled: !!documentId,
  });
};

export const useCreateBoundingBox = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateBoundingBoxRequest) => createBoundingBox(data),
    onSuccess: (newBox) => {
      // Invalidate all bounding box queries for this document
      queryClient.invalidateQueries({
        queryKey: annotationKeys.boundingBoxes(newBox.documentId),
      });
    },
  });
};

// Reply Queries

export const useReplies = (commentId: number) => {
  return useQuery({
    queryKey: annotationKeys.replies(commentId),
    queryFn: () => getReplies(commentId),
    enabled: !!commentId,
  });
};

export const useCreateReply = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateReplyRequest) => createReply(data),
    onSuccess: (newReply) => {
      // Invalidate replies for this comment
      queryClient.invalidateQueries({
        queryKey: annotationKeys.replies(newReply.commentId),
      });
    },
  });
};

// Task Queries

export const useTasks = (params?: GetTasksParams) => {
  return useQuery({
    queryKey: annotationKeys.tasks(params),
    queryFn: () => getTasks(params),
  });
};

export const useCreateTask = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateTaskRequest) => createTask(data),
    onSuccess: () => {
      // Invalidate all task queries
      queryClient.invalidateQueries({
        queryKey: annotationKeys.all,
      });
    },
  });
};

export const useUpdateTask = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ taskId, data }: { taskId: number; data: UpdateTaskRequest }) =>
      updateTask(taskId, data),
    onSuccess: () => {
      // Invalidate all task queries
      queryClient.invalidateQueries({
        queryKey: annotationKeys.all,
      });
    },
  });
};

export const useDeleteTask = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (taskId: number) => deleteTask(taskId),
    onSuccess: () => {
      // Invalidate all task queries
      queryClient.invalidateQueries({
        queryKey: annotationKeys.all,
      });
    },
  });
};
