import { apiClient } from '../client';

export interface User {
    id: string;
    name: string;
    email: string;
    role: 'admin' | 'editor' | 'viewer';
    lastLogin: string;
    status: 'active' | 'inactive';
}

export const adminService = {
    getUsers: async () => {
        const response = await apiClient.get<User[]>('/admin/users');
        return response.data;
    },

    createUser: async (user: Omit<User, 'id' | 'lastLogin'>) => {
        const response = await apiClient.post<User>('/admin/users', user);
        return response.data;
    },

    updateUser: async (id: string, user: Partial<User>) => {
        const response = await apiClient.put<User>(`/admin/users/${id}`, user);
        return response.data;
    },

    deleteUser: async (id: string) => {
        await apiClient.delete(`/admin/users/${id}`);
    },
};
