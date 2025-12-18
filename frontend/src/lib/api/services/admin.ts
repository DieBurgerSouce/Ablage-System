import { apiClient } from '../client';

export interface User {
    id: string;
    email: string;
    username: string;
    full_name?: string | null;
    is_active: boolean;
    is_superuser: boolean;
    tier: string;
    role: 'superuser' | 'admin' | 'user';
    status: 'active' | 'inactive' | 'deactivated';
    last_login?: string | null;
    created_at: string;
    // Convenience getter for display name
    name: string;
}

// Response type from backend (paginated)
interface UserListResponse {
    users: User[];
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
}

export const adminService = {
    getUsers: async (): Promise<User[]> => {
        const response = await apiClient.get<UserListResponse>('/admin/users');
        // Backend returns paginated response with users in 'users' property
        // Map to add 'name' field for display (using full_name or username)
        const users = response.data.users || [];
        return users.map(user => ({
            ...user,
            name: user.full_name || user.username,
        }));
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
