import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  Pencil,
  Trash2,
  Archive,
  RotateCcw,
  Plus,
  Package,
  Loader2,
  CreditCard,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { PaywallModal } from "@/components/billing/PaywallModal";
import { catalogClient, formatUzs, type CatalogListing } from "@/lib/catalog-client";
import { ApiError } from "@/lib/http";

const LIFECYCLE_LABEL: Record<string, { label: string; tone: "success" | "muted" | "warning" }> = {
  PUBLISHED: { label: "E'lon qilingan", tone: "success" },
  EDITED: { label: "Tahrirlangan", tone: "success" },
  DRAFT: { label: "Qoralama", tone: "muted" },
  PENDING_VERIFICATION: { label: "Tekshiruvda", tone: "warning" },
  SUSPENDED: { label: "To'xtatilgan", tone: "warning" },
  ARCHIVED: { label: "Arxivlangan", tone: "muted" },
  DELETED: { label: "O'chirilgan", tone: "muted" },
};

export function LifecycleBadge({
  state,
  awaitingPayment,
}: {
  state?: string;
  /** Listing paywall (2026-08-23): a DRAFT listing held for payment reads as a distinct state
   * from an ordinary unfinished draft -- same underlying `lifecycleState`, different reason. */
  awaitingPayment?: boolean;
}) {
  const info =
    state === "DRAFT" && awaitingPayment
      ? { label: "To'lov kutilmoqda", tone: "warning" as const }
      : (state && LIFECYCLE_LABEL[state]) || { label: state ?? "—", tone: "muted" as const };
  return (
    <Badge
      variant="secondary"
      className={
        info.tone === "success"
          ? "bg-success/10 text-success"
          : info.tone === "warning"
            ? "bg-amber-500/10 text-amber-600"
            : "bg-muted text-muted-foreground"
      }
    >
      {info.label}
    </Badge>
  );
}

const ARCHIVABLE_STATES = new Set(["PUBLISHED", "EDITED", "PENDING_VERIFICATION"]);
const RESTORABLE_STATES = new Set(["ARCHIVED", "SUSPENDED"]);

function RowActions({ listing }: { listing: CatalogListing }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<"archive" | "restore" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["catalog", "my-listings"] });

  const toggleArchive = async () => {
    setError(null);
    setBusy(ARCHIVABLE_STATES.has(listing.lifecycleState ?? "") ? "archive" : "restore");
    try {
      await catalogClient.changeListingStatus(
        listing.id,
        ARCHIVABLE_STATES.has(listing.lifecycleState ?? "") ? "ARCHIVE" : "RESTORE",
      );
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Amalni bajarib bo'lmadi.");
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!window.confirm(`"${listing.title}" e'lonini o'chirmoqchimisiz?`)) return;
    setError(null);
    setBusy("delete");
    try {
      await catalogClient.deleteListing(listing.id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "O'chirib bo'lmadi.");
      setBusy(null);
    }
  };

  const canToggle =
    ARCHIVABLE_STATES.has(listing.lifecycleState ?? "") ||
    RESTORABLE_STATES.has(listing.lifecycleState ?? "");

  return (
    <div className="flex items-center justify-end gap-1">
      {error && <span className="mr-2 text-[11px] text-destructive">{error}</span>}
      {listing.lifecycleState === "DRAFT" && listing.awaitingPayment && (
        <>
          <button
            type="button"
            onClick={() => setPaying(true)}
            aria-label="To'lash"
            title="To'lash"
            className="flex size-8 items-center justify-center rounded-lg text-primary transition hover:bg-primary/10"
          >
            <CreditCard className="size-3.5" />
          </button>
          {paying && (
            <PaywallModal
              open
              onOpenChange={(open) => !open && setPaying(false)}
              listingId={listing.id}
              categoryId={listing.categoryId}
              onActivated={() => {
                setPaying(false);
                refresh();
                navigate({ to: "/properties/$slug", params: { slug: listing.id } });
              }}
            />
          )}
        </>
      )}
      <Link
        to="/list/$listingId"
        params={{ listingId: listing.id }}
        aria-label="Tahrirlash"
        title="Tahrirlash"
        className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground"
      >
        <Pencil className="size-3.5" />
      </Link>
      {canToggle && (
        <button
          type="button"
          onClick={toggleArchive}
          disabled={busy !== null}
          aria-label={
            ARCHIVABLE_STATES.has(listing.lifecycleState ?? "") ? "Arxivlash" : "Faollashtirish"
          }
          title={
            ARCHIVABLE_STATES.has(listing.lifecycleState ?? "") ? "Arxivlash" : "Faollashtirish"
          }
          className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          {busy === "archive" || busy === "restore" ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : ARCHIVABLE_STATES.has(listing.lifecycleState ?? "") ? (
            <Archive className="size-3.5" />
          ) : (
            <RotateCcw className="size-3.5" />
          )}
        </button>
      )}
      <button
        type="button"
        onClick={remove}
        disabled={busy !== null}
        aria-label="O'chirish"
        title="O'chirish"
        className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
      >
        {busy === "delete" ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Trash2 className="size-3.5" />
        )}
      </button>
    </div>
  );
}

export function ListingsTable({ listings }: { listings: CatalogListing[] }) {
  if (listings.length === 0) {
    return (
      <EmptyState
        icon={Package}
        title="Hali e'lon joylanmagan"
        description="Birinchi e'loningizni qo'shib, mijozlarga ko'rinishni boshlang."
        action={
          <Link
            to="/list"
            className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
          >
            <Plus className="size-3.5" /> E'lon joylash
          </Link>
        }
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Nomi</TableHead>
          <TableHead>Narx</TableHead>
          <TableHead>Holati</TableHead>
          <TableHead>Sana</TableHead>
          <TableHead className="text-right">Amallar</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {listings.map((l) => (
          <TableRow key={l.id} className="group transition hover:bg-muted/50">
            <TableCell className="font-medium text-foreground">{l.title}</TableCell>
            <TableCell>{formatUzs(l.price?.amount)}</TableCell>
            <TableCell>
              <LifecycleBadge state={l.lifecycleState} awaitingPayment={l.awaitingPayment} />
            </TableCell>
            <TableCell className="text-xs text-muted-foreground">
              {new Date(l.createdAt).toLocaleDateString()}
            </TableCell>
            <TableCell>
              <RowActions listing={l} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
