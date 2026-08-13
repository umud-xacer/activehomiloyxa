/**
 * Reusable "save to favorites" heart button, backed by the real `favoritesApi`
 * (POST/DELETE /me/favorites) -- shared by every listing card (PropertyCard, GoodsCard,
 * ServiceCard, VenueCard) and both listing detail pages, so heart state stays consistent
 * everywhere a given listing appears without each caller re-deriving it.
 */
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Heart } from "lucide-react";
import { useMe } from "@/features/auth/useAuth";
import { favoritesApi } from "@/lib/favorites-client";

/** All favorited listing ids for the current account, as a `Set` for O(1) membership checks.
 * Disabled while logged out (an anonymous `GET /me/favorites` would just 401). Shares its cache
 * with `/favorites` page's own list query via the `["favorites", ...]` key prefix, so adding or
 * removing anywhere invalidates both. */
export function useFavoriteIds() {
  const { data: account } = useMe();
  return useQuery({
    queryKey: ["favorites", "ids"],
    queryFn: () => favoritesApi.list().then((page) => new Set(page.items.map((i) => i.listingId))),
    enabled: !!account,
    staleTime: 30_000,
  });
}

export function FavoriteButton({
  listingId,
  size = "md",
  variant = "overlay",
  className = "",
}: {
  listingId: string;
  size?: "sm" | "md";
  /** "overlay" = filled white circle for sitting on top of a photo (card thumbnails); "outline"
   * = bordered circle matching the detail-page action row. */
  variant?: "overlay" | "outline";
  className?: string;
}) {
  const navigate = useNavigate();
  const { data: account } = useMe();
  const { data: favoriteIds } = useFavoriteIds();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<boolean | null>(null);

  const isFavorited = pending ?? favoriteIds?.has(listingId) ?? false;

  const toggle = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!account) {
      navigate({ to: "/auth/sign-in" });
      return;
    }
    if (busy) return;
    const next = !isFavorited;
    setBusy(true);
    setPending(next);
    try {
      if (next) {
        await favoritesApi.add(listingId);
      } else {
        await favoritesApi.remove(listingId);
      }
      await queryClient.invalidateQueries({ queryKey: ["favorites"] });
    } catch {
      setPending(!next);
    } finally {
      setBusy(false);
    }
  };

  const dims = size === "sm" ? "size-8" : "size-9";
  const iconDims = size === "sm" ? "size-3.5" : "size-4";
  const shell =
    variant === "overlay"
      ? "bg-white/90 text-foreground shadow-soft backdrop-blur hover:bg-white"
      : "border border-border bg-card hover:bg-muted";

  return (
    <button
      type="button"
      aria-label={isFavorited ? "Saqlangandan olib tashlash" : "Saqlash"}
      aria-pressed={isFavorited}
      onClick={toggle}
      disabled={busy}
      className={`inline-flex shrink-0 items-center justify-center rounded-full transition disabled:opacity-70 ${dims} ${shell} ${className}`}
    >
      <Heart
        className={`${iconDims} transition-colors ${isFavorited ? "fill-destructive text-destructive" : ""}`}
      />
    </button>
  );
}
