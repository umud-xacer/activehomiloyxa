import { queryOptions } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { PropertyQuery } from "./types";

export const propertyListOptions = (query: PropertyQuery = {}) =>
  queryOptions({
    queryKey: ["properties", "list", query],
    queryFn: () => apiClient.properties.list(query),
    staleTime: 60_000,
  });

export const propertyOptions = (idOrSlug: string) =>
  queryOptions({
    queryKey: ["properties", "detail", idOrSlug],
    queryFn: () => apiClient.properties.get(idOrSlug),
    staleTime: 60_000,
  });

export const featuredPropertiesOptions = (limit = 8) =>
  queryOptions({
    queryKey: ["properties", "featured", limit],
    queryFn: () => apiClient.properties.featured(limit),
    staleTime: 5 * 60_000,
  });

export const nearbyPropertiesOptions = (id: string, limit = 6) =>
  queryOptions({
    queryKey: ["properties", "nearby", id, limit],
    queryFn: () => apiClient.properties.nearby(id, limit),
    staleTime: 60_000,
  });
