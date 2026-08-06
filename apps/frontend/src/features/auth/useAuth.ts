import { useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi, type Account } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";

export const meQueryKey = ["auth", "me"] as const;

/**
 * Resolves the current session, backed by GET /me.
 * `data` is `null` (not an error) when there is no active session — 401 is
 * an expected, steady-state response for logged-out visitors.
 */
export function useMe() {
  return useQuery<Account | null>({
    queryKey: meQueryKey,
    queryFn: async () => {
      try {
        return await authApi.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

/** Call after any successful login/register/logout to refresh session-dependent UI. */
export function useInvalidateAuth() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: meQueryKey });
}
