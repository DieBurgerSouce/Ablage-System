import { QueryClient } from "@tanstack/react-query"
import { QUERY_SEMI_STATIC } from "./query-config"

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            ...QUERY_SEMI_STATIC, // 5min staleTime, 30min gcTime
            retry: 1,
            refetchOnWindowFocus: false,
        },
    },
})
