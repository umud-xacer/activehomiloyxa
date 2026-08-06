import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Loader2, ImagePlus, X, Trash2 } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { profilesApi } from "@/lib/profiles-api";
import { mediaApi, mediaAssetUrl } from "@/lib/media-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/business-profile/$id")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Biznes profilni boshqarish — ActiveHome" }] }),
  component: Page,
});

function Page() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: profile, isLoading } = useQuery({
    queryKey: ["business-profile", id],
    queryFn: () => profilesApi.getBusinessProfile(id),
  });
  const { data: portfolio = [] } = useQuery({
    queryKey: ["business-profile", id, "portfolio"],
    queryFn: () => profilesApi.listPortfolio(id),
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [address, setAddress] = useState("");
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!profile) return;
    setName(profile.name.uz_latn ?? "");
    setDescription(profile.description?.uz_latn ?? "");
    setAddress(profile.address ?? "");
  }, [profile]);

  const refreshProfile = () => queryClient.invalidateQueries({ queryKey: ["business-profile", id] });
  const refreshPortfolio = () => queryClient.invalidateQueries({ queryKey: ["business-profile", id, "portfolio"] });

  const saveMutation = useMutation({
    mutationFn: () => profilesApi.updateBusinessProfile(id, { name, description, address }),
    onSuccess: () => {
      refreshProfile();
      setSavedMsg("Saqlandi");
      setTimeout(() => setSavedMsg(null), 2000);
    },
    onError: (err) => setSavedMsg(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik"),
  });

  const archiveMutation = useMutation({
    mutationFn: () => profilesApi.archiveBusinessProfile(id),
    onSuccess: () => navigate({ to: "/dashboard/seller" }),
  });

  const removePortfolioItem = useMutation({
    mutationFn: (itemId: string) => profilesApi.removePortfolioItem(id, itemId),
    onSuccess: refreshPortfolio,
  });

  const onPickPortfolioImage = async (files: FileList | null) => {
    if (!files || !files[0]) return;
    setUploading(true);
    try {
      const asset = await mediaApi.uploadImage(files[0]);
      await profilesApi.addPortfolioItem(id, asset.id);
      refreshPortfolio();
    } catch (err) {
      setSavedMsg(err instanceof Error ? err.message : "Rasm yuklashda xatolik");
    } finally {
      setUploading(false);
    }
  };

  if (isLoading || !profile) {
    return (
      <AppShell>
        <PageHeader eyebrow="Seller" title="Biznes profil" />
        <div className="mx-auto max-w-2xl px-6 py-12">
          <div className="h-64 animate-pulse rounded-2xl bg-muted" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader eyebrow="Seller" title="Biznes profilni boshqarish" description={profile.slug} />
      <div className="mx-auto max-w-2xl space-y-6 px-6 py-12">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            saveMutation.mutate();
          }}
          className="space-y-4 rounded-2xl border border-border bg-card/50 p-4"
        >
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Nomi</span>
            <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-foreground" />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Tavsif</span>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="mt-1.5 w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-foreground" />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Manzil</span>
            <input value={address} onChange={(e) => setAddress(e.target.value)} className="mt-1.5 w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-foreground" />
          </label>
          {savedMsg && <p className="text-xs text-muted-foreground">{savedMsg}</p>}
          <div className="flex items-center justify-between">
            <button
              type="submit"
              disabled={saveMutation.isPending}
              className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
            >
              {saveMutation.isPending && <Loader2 className="size-4 animate-spin" />} Saqlash
            </button>
            <button
              type="button"
              onClick={() => confirm("Profilni arxivlashni tasdiqlaysizmi?") && archiveMutation.mutate()}
              className="inline-flex items-center gap-1.5 rounded-full border border-destructive/30 px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/10"
            >
              <Trash2 className="size-3.5" /> Profilni arxivlash
            </button>
          </div>
        </form>

        <div className="rounded-2xl border border-border bg-card/50 p-4">
          <span className="text-xs font-semibold text-foreground/80">Portfolio</span>
          <div className="mt-1.5 grid grid-cols-3 gap-2 sm:grid-cols-4">
            {portfolio.map((item) => (
              <div key={item.id} className="group relative aspect-square overflow-hidden rounded-xl border border-border">
                <img src={mediaAssetUrl(item.mediaAssetId, "thumbnail")} alt={item.caption?.uz_latn ?? ""} className="size-full object-cover" />
                <button
                  type="button"
                  onClick={() => removePortfolioItem.mutate(item.id)}
                  className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity group-hover:opacity-100"
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
            <label className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-border bg-card/50 text-muted-foreground hover:bg-muted">
              {uploading ? <Loader2 className="size-5 animate-spin" /> : <ImagePlus className="size-5" />}
              <span className="text-[10px]">Qo'shish</span>
              <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => onPickPortfolioImage(e.target.files)} disabled={uploading} />
            </label>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
