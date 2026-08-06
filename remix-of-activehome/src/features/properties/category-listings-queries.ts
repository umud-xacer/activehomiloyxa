import { queryOptions } from "@tanstack/react-query";
import { listingApi, type BackendListing, type BackendCategory } from "@/lib/listing-api";

export interface CategoryListings {
  category: BackendCategory | null;
  listings: BackendListing[];
}

export const categoryListingsOptions = (categoryPath: string) =>
  queryOptions({
    queryKey: ["categoryListings", categoryPath],
    queryFn: async (): Promise<CategoryListings> => {
      const categories = await listingApi.listCategories();
      const category = categories.find((c) => c.path === categoryPath) ?? null;
      if (!category) return { category: null, listings: [] };
      const listings = await listingApi.listListings({ categoryId: category.id, limit: 50 });
      return { category, listings };
    },
    staleTime: 60_000,
  });
