/**
 * Favorites API client — matches the "Favorites" section of contracts/openapi.yaml
 * (`GET/POST /me/favorites`, `DELETE /me/favorites/{listingId}`).
 */
import { http } from "@/lib/http";

export interface Favorite {
  listingId: string;
  createdAt: string;
}

interface FavoritePage {
  items: Favorite[];
  page: { limit: number; nextCursor: string | null; total: number | null };
}

export const favoritesApi = {
  list(cursor?: string, limit = 40): Promise<FavoritePage> {
    return http.get<FavoritePage>("/me/favorites", { params: { cursor, limit } });
  },
  add(listingId: string): Promise<Favorite> {
    return http.post<Favorite>("/me/favorites", { listingId });
  },
  remove(listingId: string): Promise<void> {
    return http.delete<void>(`/me/favorites/${listingId}`);
  },
};
