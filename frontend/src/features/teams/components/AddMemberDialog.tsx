/**
 * AddMemberDialog Component
 *
 * Dialog zum Hinzufuegen von neuen Mitgliedern zu einem Team.
 */

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Loader2, Check, ChevronsUpDown, UserPlus } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { TeamMemberRole } from '../api/teams-api';
import { useAddMember } from '../hooks/use-teams';
import apiClient from '@/lib/api/client';

interface AddMemberDialogProps {
  teamId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface User {
  id: string;
  username: string;
  email: string;
  full_name?: string;
}

const addMemberSchema = z.object({
  user_id: z.string().uuid('Bitte waehlen Sie einen Benutzer aus'),
  role: z.enum(['member', 'lead', 'admin', 'deputy', 'observer']),
});

type AddMemberFormValues = z.infer<typeof addMemberSchema>;

const roleOptions: { value: TeamMemberRole; label: string; description: string }[] = [
  { value: 'member', label: 'Mitglied', description: 'Standard-Zugriff auf Team-Ressourcen' },
  { value: 'observer', label: 'Beobachter', description: 'Nur lesender Zugriff' },
  { value: 'deputy', label: 'Stellvertretung', description: 'Kann bei Abwesenheit vertreten' },
  { value: 'lead', label: 'Leitung', description: 'Teamleitung mit erweitertem Zugriff' },
  { value: 'admin', label: 'Admin', description: 'Vollstaendige Verwaltungsrechte' },
];

export function AddMemberDialog({ teamId, open, onOpenChange }: AddMemberDialogProps) {
  const [userSearchOpen, setUserSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const addMember = useAddMember(teamId);

  // Search for users
  const { data: users, isLoading: isLoadingUsers } = useQuery({
    queryKey: ['users', 'search', searchQuery],
    queryFn: async () => {
      const response = await apiClient.get<{ users: User[]; total: number }>('/admin/users', {
        params: { search: searchQuery, page_size: 20 },
      });
      return response.data.users;
    },
    enabled: open && searchQuery.length > 0,
  });

  const form = useForm<AddMemberFormValues>({
    resolver: zodResolver(addMemberSchema),
    defaultValues: {
      user_id: '',
      role: 'member',
    },
  });

  const selectedUserId = form.watch('user_id');
  const selectedUser = users?.find((u) => u.id === selectedUserId);

  const onSubmit = async (values: AddMemberFormValues) => {
    try {
      await addMember.mutateAsync(values);
      form.reset();
      onOpenChange(false);
    } catch {
      // Error handling is done in the mutation
    }
  };

  const getInitials = (user: User) => {
    if (user.full_name) {
      const parts = user.full_name.split(' ');
      if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
      }
      return user.full_name.substring(0, 2).toUpperCase();
    }
    return user.username.substring(0, 2).toUpperCase();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            Mitglied hinzufuegen
          </DialogTitle>
          <DialogDescription>
            Fuegen Sie einen bestehenden Benutzer zum Team hinzu.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="user_id"
              render={({ field }) => (
                <FormItem className="flex flex-col">
                  <FormLabel>Benutzer</FormLabel>
                  <Popover open={userSearchOpen} onOpenChange={setUserSearchOpen}>
                    <PopoverTrigger asChild>
                      <FormControl>
                        <Button
                          variant="outline"
                          role="combobox"
                          className={cn(
                            'w-full justify-between',
                            !field.value && 'text-muted-foreground'
                          )}
                        >
                          {selectedUser ? (
                            <div className="flex items-center gap-2">
                              <Avatar className="h-6 w-6">
                                <AvatarFallback className="text-xs">
                                  {getInitials(selectedUser)}
                                </AvatarFallback>
                              </Avatar>
                              <span>
                                {selectedUser.full_name || selectedUser.username}
                              </span>
                            </div>
                          ) : (
                            'Benutzer suchen...'
                          )}
                          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </FormControl>
                    </PopoverTrigger>
                    <PopoverContent className="w-[350px] p-0">
                      <Command shouldFilter={false}>
                        <CommandInput
                          placeholder="Name oder E-Mail suchen..."
                          value={searchQuery}
                          onValueChange={setSearchQuery}
                        />
                        <CommandList>
                          {isLoadingUsers && (
                            <div className="flex justify-center py-4">
                              <Loader2 className="h-4 w-4 animate-spin" />
                            </div>
                          )}
                          {!isLoadingUsers && searchQuery && (!users || users.length === 0) && (
                            <CommandEmpty>Keine Benutzer gefunden</CommandEmpty>
                          )}
                          {!isLoadingUsers && searchQuery.length === 0 && (
                            <CommandEmpty>Geben Sie einen Suchbegriff ein</CommandEmpty>
                          )}
                          <CommandGroup>
                            {users?.map((user) => (
                              <CommandItem
                                key={user.id}
                                value={user.id}
                                onSelect={() => {
                                  form.setValue('user_id', user.id);
                                  setUserSearchOpen(false);
                                }}
                              >
                                <div className="flex items-center gap-2 flex-1">
                                  <Avatar className="h-8 w-8">
                                    <AvatarFallback>{getInitials(user)}</AvatarFallback>
                                  </Avatar>
                                  <div className="flex flex-col">
                                    <span className="font-medium">
                                      {user.full_name || user.username}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                      {user.email}
                                    </span>
                                  </div>
                                </div>
                                <Check
                                  className={cn(
                                    'ml-auto h-4 w-4',
                                    field.value === user.id ? 'opacity-100' : 'opacity-0'
                                  )}
                                />
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                  <FormDescription>
                    Suchen Sie nach Name oder E-Mail-Adresse
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Rolle</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Waehlen Sie eine Rolle" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {roleOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          <div>
                            <div className="font-medium">{option.label}</div>
                            <div className="text-xs text-muted-foreground">
                              {option.description}
                            </div>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Abbrechen
              </Button>
              <Button type="submit" disabled={addMember.isPending || !selectedUserId}>
                {addMember.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Hinzufuegen
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
