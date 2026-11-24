import { isServer, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/shared";

const isClientError = (error: unknown) =>
  error instanceof ApiError && error.status < 500;

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000, // server-seeded data stays fresh; no refetch right after hydration
        retry: (failures, error) => !isClientError(error) && failures < 2,
      },
    },
    queryCache: new QueryCache({
      onError: (error) => {
        // Session expired or revoked: any 401 from the API sends the user to sign in.
        if (!isServer && error instanceof ApiError && error.status === 401) {
          window.location.assign("/sign-in");
        }
      },
    }),
  });
}

let browserQueryClient: QueryClient | undefined;

/** A fresh client per server render; one shared client in the browser. */
export function getQueryClient() {
  if (isServer) return makeQueryClient();
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}
