import { queryOptions } from "@tanstack/react-query";
import { listingApi } from "@/lib/listing-api";
import { apiClient } from "@/lib/api-client";
import type { Property } from "./types";

export const favoriteIdsOptions = () =>
  queryOptions({
    queryKey: ["favorites", "ids"],
    queryFn: () => listingApi.listFavoriteIds(),
    staleTime: 30_000,
  });

export const favoritePropertiesOptions = (limit?: number) =>
  queryOptions({
    queryKey: ["favorites", "properties", limit],
    queryFn: async (): Promise<Property[]> => {
      const ids = await listingApi.listFavoriteIds();
      const wanted = limit ? ids.slice(0, limit) : ids;
      const all = await Promise.all(wanted.map((id) => apiClient.properties.get(id)));
      return all.filter((p): p is Property => p !== null);
    },
    staleTime: 30_000,
  });
