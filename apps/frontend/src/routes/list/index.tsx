import { useEffect, useMemo, useState, type FormEvent } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Tag,
  ImagePlus,
  X,
  ArrowLeft,
  Building2,
  ChevronRight,
  Phone,
  Mail,
  Globe,
  MapPin,
  Save,
  Pencil,
  Plus,
} from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { catalogClient, uploadMediaFile, type CategorySummary } from "@/lib/catalog-client";
import { categoryLabel } from "@/components/site/CategoryCarousel";
import { DynamicCategoryForm } from "@/features/listings/DynamicCategoryForm";
import { authApi } from "@/lib/auth-client";
import {
  businessProfilesApi,
  PROFILE_TYPE_LABEL,
  type ProfileType,
} from "@/lib/business-profiles-client";
import type { Currency } from "@/features/properties/types";
import { useMe, useInvalidateAuth } from "@/features/auth/useAuth";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/list/")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "E'lon joylash — ActiveHome" },
      { name: "description", content: "Kategoriyani tanlang va e'loningizni joylashtiring." },
    ],
  }),
  component: Page,
});

const CURRENCIES: Currency[] = ["UZS", "USD", "EUR", "RUB"];

/** Drills into the category tree one level at a time (a category with children shows them
 * instead of jumping straight to the listing form — but since every category, leaf or not,
 * binds its own `formDefinitionId`, the breadcrumb also lets the user list directly under the
 * parent they're currently browsing rather than forcing them all the way to a leaf). */
function CategoryPicker({
  categories,
  path,
  onDrill,
  onSelect,
  onBreadcrumb,
}: {
  categories: CategorySummary[];
  path: CategorySummary[];
  onDrill: (cat: CategorySummary) => void;
  onSelect: (cat: CategorySummary) => void;
  onBreadcrumb: (index: number) => void;
}) {
  const parentId = path.length > 0 ? path[path.length - 1].id : null;
  const visible = categories.filter((c) => c.status === "ACTIVE" && c.parentId === parentId);
  const current = path.length > 0 ? path[path.length - 1] : null;

  return (
    <div className="space-y-4">
      {path.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
          <button
            type="button"
            onClick={() => onBreadcrumb(-1)}
            className="rounded-full px-2 py-1 font-medium hover:bg-muted hover:text-foreground"
          >
            Barcha kategoriyalar
          </button>
          {path.map((cat, i) => (
            <span key={cat.id} className="flex items-center gap-1">
              <ChevronRight className="size-3.5" />
              <button
                type="button"
                onClick={() => onBreadcrumb(i)}
                className={`rounded-full px-2 py-1 font-medium hover:bg-muted hover:text-foreground ${
                  i === path.length - 1 ? "text-foreground" : ""
                }`}
              >
                {categoryLabel(cat.name, "uz")}
              </button>
            </span>
          ))}
        </div>
      )}

      {current && (
        <button
          type="button"
          onClick={() => onSelect(current)}
          className="w-full rounded-2xl border border-dashed border-primary/40 bg-primary/5 px-5 py-3 text-left text-sm font-medium text-primary transition hover:bg-primary/10"
        >
          "{categoryLabel(current.name, "uz")}" bo'limida to'g'ridan-to'g'ri e'lon joylash
        </button>
      )}

      {visible.length === 0 ? (
        current ? null : (
          <EmptyState title="Kategoriyalar topilmadi" />
        )
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {visible.map((cat) => {
            const hasChildren = categories.some(
              (c) => c.status === "ACTIVE" && c.parentId === cat.id,
            );
            return (
              <button
                key={cat.id}
                type="button"
                onClick={() => (hasChildren ? onDrill(cat) : onSelect(cat))}
                className="group relative flex flex-col items-center gap-2.5 rounded-2xl border border-border bg-card p-5 text-center shadow-soft transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-elevated"
              >
                {hasChildren && (
                  <ChevronRight className="absolute right-2.5 top-2.5 size-4 text-muted-foreground" />
                )}
                <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary transition group-hover:scale-105">
                  <Tag className="size-5" />
                </div>
                <span className="font-display text-sm font-semibold text-foreground">
                  {categoryLabel(cat.name, "uz")}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** A single "phone/email"-style repeatable text field — mirrors
 * `dashboard/business-profile.tsx`'s `TextListField` (kept local here since this route doesn't
 * otherwise depend on that page). */
function RepeatableField({
  icon: Icon,
  label,
  placeholder,
  values,
  onChange,
}: {
  icon: typeof Phone;
  label: string;
  placeholder: string;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Icon className="size-3.5" /> {label}
        </label>
        <button
          type="button"
          onClick={() => onChange([...values, ""])}
          className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
        >
          <Plus className="size-3.5" /> Qo'shish
        </button>
      </div>
      <div className="mt-1.5 space-y-2">
        {values.map((value, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={value}
              onChange={(e) => onChange(values.map((v, idx) => (idx === i ? e.target.value : v)))}
              placeholder={placeholder}
              className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
            />
            <button
              type="button"
              onClick={() => onChange(values.filter((_, idx) => idx !== i))}
              className="rounded-lg p-2 text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Yuridik shaxslar uchun alohida, soddaroq forma — faqat kompaniya haqidagi ma'lumot (nomi,
 * yo'nalishi, tavsif, kontakt), jismoniy shaxsning kategoriya-asosidagi e'lon formasidan butunlay
 * farqli. `businessProfilesApi.create` faqat nomi/yo'nalishi/manzilni qabul qiladi, shuning uchun
 * bitta forma ikkita chaqiruvga (create + update) bo'linadi -- foydalanuvchi buni bitta qadam
 * sifatida ko'radi. */
function CompanyProfileForm({ onCreated }: { onCreated: () => void }) {
  const invalidateAuth = useInvalidateAuth();
  const [name, setName] = useState("");
  const [profileType, setProfileType] = useState<ProfileType>("SERVICE_PROVIDER");
  const [description, setDescription] = useState("");
  const [address, setAddress] = useState("");
  const [phones, setPhones] = useState<string[]>([""]);
  const [emails, setEmails] = useState<string[]>([""]);
  const [website, setWebsite] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const profile = await businessProfilesApi.create({
        profileType,
        name: name.trim(),
        address: address.trim() || undefined,
      });
      const cleanPhones = phones.map((p) => p.trim()).filter(Boolean);
      const cleanEmails = emails.map((em) => em.trim()).filter(Boolean);
      if (description.trim() || cleanPhones.length || cleanEmails.length || website.trim()) {
        await businessProfilesApi.update(profile.id, {
          description: description.trim() || undefined,
          contacts: {
            phones: cleanPhones,
            emails: cleanEmails,
            website: website.trim() || undefined,
          },
        });
      }
      await invalidateAuth();
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kompaniya profilini yaratishda xatolik.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            Kompaniya nomi <span className="text-destructive">*</span>
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={200}
            placeholder="masalan: ActiveHome Qurilish MChJ"
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            Yo'nalishi / faoliyat maqsadi <span className="text-destructive">*</span>
          </label>
          <select
            value={profileType}
            onChange={(e) => setProfileType(e.target.value as ProfileType)}
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          >
            {Object.entries(PROFILE_TYPE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Tavsif</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Kompaniyangiz nima bilan shug'ullanadi, qanday xizmat/mahsulot taklif qiladi"
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <MapPin className="size-3.5" /> Manzil
          </label>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Shahar, tuman, ko'cha"
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <RepeatableField
          icon={Phone}
          label="Telefon raqamlari"
          placeholder="+998 90 123 45 67"
          values={phones}
          onChange={setPhones}
        />
        <RepeatableField
          icon={Mail}
          label="Email manzillari"
          placeholder="info@company.uz"
          values={emails}
          onChange={setEmails}
        />
      </div>

      <div>
        <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Globe className="size-3.5" /> Veb-sayt
        </label>
        <input
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
          placeholder="https://company.uz"
          className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
        />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <button
        type="submit"
        disabled={submitting || !name.trim()}
        className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-50"
      >
        {submitting ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
        Kompaniya profilini saqlash
      </button>
    </form>
  );
}

/** Shown to a LEGAL_ENTITY user who already owns a business profile, before the (unchanged)
 * item-listing form below -- makes clear which identity they're posting as and that the company
 * profile itself is edited elsewhere, not re-entered here. */
function ActingAsProfileBanner({ profileId }: { profileId: string }) {
  const { data: profile } = useQuery({
    queryKey: ["business-profiles", profileId],
    queryFn: () => businessProfilesApi.get(profileId),
  });

  return (
    <div className="mb-8 flex flex-wrap items-center gap-4 rounded-2xl border border-dashed border-border bg-card/60 p-5">
      <Building2 className="size-6 shrink-0 text-primary" />
      <div className="flex-1 text-sm text-foreground">
        {profile ? (
          <>
            Siz <span className="font-semibold">{profile.name.uz_latn}</span> nomidan e'lon
            joylaysiz.
          </>
        ) : (
          "Siz kompaniyangiz nomidan e'lon joylaysiz."
        )}
      </div>
      <Link
        to="/dashboard/business-profile"
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition hover:bg-muted"
      >
        <Pencil className="size-3.5" /> Kompaniya profilini tahrirlash
      </Link>
    </div>
  );
}

function Page() {
  const { data: account } = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: categories = [], isLoading: categoriesLoading } = useQuery({
    queryKey: ["catalog", "categories", "all"],
    queryFn: () => catalogClient.listCategories(),
  });

  const [categoryPath, setCategoryPath] = useState<CategorySummary[]>([]);
  const [category, setCategory] = useState<CategorySummary | null>(null);
  const { data: form, isLoading: formLoading } = useQuery({
    queryKey: ["catalog", "category-form", category?.id],
    queryFn: () => catalogClient.getCategoryForm(category!.id),
    enabled: !!category,
  });

  const [listingType, setListingType] = useState<"ADVERTISEMENT" | "PRODUCT" | "SERVICE">(
    "ADVERTISEMENT",
  );
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priceAmount, setPriceAmount] = useState("");
  const [currency, setCurrency] = useState<Currency>("UZS");
  const [attributes, setAttributes] = useState<Record<string, unknown>>({});
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLegalEntity = account?.accountKind === "LEGAL_ENTITY";
  const ownedProfileIds = account?.ownedProfileIds ?? [];
  const needsBusinessProfile = isLegalEntity && ownedProfileIds.length === 0;

  useEffect(() => {
    setAttributes({});
  }, [category?.id]);

  const onFilesChange = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => [...prev, ...Array.from(list)].slice(0, 8));
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!category) return;
    setError(null);
    setSubmitting(true);
    try {
      if (isLegalEntity && ownedProfileIds.length > 0) {
        await authApi.switchActingProfile(ownedProfileIds[0]);
      }

      const imageMediaAssetIds: string[] = [];
      for (const file of files) {
        const ticket = await catalogClient.initMediaUpload(file);
        await uploadMediaFile(ticket, file);
        imageMediaAssetIds.push(ticket.mediaAssetId);
      }

      const listing = await catalogClient.createListing({
        listingType,
        categoryId: category.id,
        title,
        description: description || undefined,
        attributes,
        price: priceAmount ? { amount: priceAmount, currency } : undefined,
        imageMediaAssetIds: imageMediaAssetIds.length > 0 ? imageMediaAssetIds : undefined,
        publish: true,
      });

      await queryClient.invalidateQueries({ queryKey: ["catalog", "my-listings"] });
      navigate({ to: "/properties/$slug", params: { slug: listing.id } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "E'lonni joylashda xatolik yuz berdi.");
      setSubmitting(false);
    }
  };

  const canSubmit = useMemo(
    () => !!category && title.trim().length > 0 && !submitting,
    [category, title, submitting],
  );

  if (needsBusinessProfile) {
    return (
      <AppShell>
        <PageHeader
          eyebrow="Yuridik shaxs"
          title="Kompaniya profilini to'ldiring"
          description="Yuridik shaxs sifatida e'lon joylashdan oldin kompaniyangiz haqida qisqacha ma'lumot bering — bu jismoniy shaxs e'lon formasidan farqli, alohida kompaniya profili."
          crumbs={[{ label: "Bosh sahifa", to: "/" }, { label: "E'lon joylash" }]}
        />
        <div className="mx-auto max-w-3xl px-6 py-10">
          <CompanyProfileForm onCreated={() => navigate({ to: "/dashboard/business-profile" })} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="E'lon joylash"
        title={category ? categoryLabel(category.name, "uz") : "Kategoriyani tanlang"}
        description={
          category
            ? "Quyidagi maydonlarni to'ldiring — e'loningiz darhol e'lon qilinadi."
            : "E'loningiz qaysi kategoriyaga tegishli ekanini tanlang."
        }
        crumbs={[{ label: "Bosh sahifa", to: "/" }, { label: "E'lon joylash" }]}
      />

      <div className="mx-auto max-w-4xl px-6 py-10">
        {isLegalEntity && ownedProfileIds.length > 0 && (
          <ActingAsProfileBanner profileId={ownedProfileIds[0]} />
        )}

        {!category ? (
          categoriesLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Kategoriyalar yuklanmoqda…
            </div>
          ) : categories.length === 0 ? (
            <EmptyState title="Kategoriyalar topilmadi" />
          ) : (
            <CategoryPicker
              categories={categories}
              path={categoryPath}
              onDrill={(cat) => setCategoryPath((prev) => [...prev, cat])}
              onSelect={setCategory}
              onBreadcrumb={(index) => setCategoryPath((prev) => prev.slice(0, index + 1))}
            />
          )
        ) : (
          <form onSubmit={onSubmit} className="space-y-8">
            <button
              type="button"
              onClick={() => setCategory(null)}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="size-4" /> Kategoriyani almashtirish
            </button>

            <div>
              <h3 className="font-display text-sm font-semibold text-foreground">
                Asosiy ma'lumot
              </h3>
              <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                    Sarlavha <span className="text-destructive">*</span>
                  </label>
                  <input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    required
                    maxLength={200}
                    className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                    Tavsif
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={4}
                    className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                    Narxi
                  </label>
                  <input
                    type="number"
                    value={priceAmount}
                    onChange={(e) => setPriceAmount(e.target.value)}
                    min={0}
                    className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                    Valyuta
                  </label>
                  <select
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value as Currency)}
                    className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                  >
                    {CURRENCIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                    E'lon turi
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {(
                      [
                        { key: "ADVERTISEMENT", label: "E'lon" },
                        { key: "PRODUCT", label: "Mahsulot" },
                        { key: "SERVICE", label: "Xizmat" },
                      ] as const
                    ).map((opt) => (
                      <button
                        key={opt.key}
                        type="button"
                        onClick={() => setListingType(opt.key)}
                        className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                          listingType === opt.key
                            ? "bg-primary text-primary-foreground shadow-soft"
                            : "border border-border bg-background text-foreground/70 hover:text-foreground"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h3 className="font-display text-sm font-semibold text-foreground">Rasmlar</h3>
              <div className="mt-3 flex flex-wrap gap-3">
                {files.map((file, i) => (
                  <div
                    key={i}
                    className="relative size-20 overflow-hidden rounded-xl border border-border"
                  >
                    <img
                      src={URL.createObjectURL(file)}
                      alt=""
                      className="size-full object-cover"
                    />
                    <button
                      type="button"
                      onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                      className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/60 text-white"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                ))}
                {files.length < 8 && (
                  <label className="flex size-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-border text-muted-foreground transition hover:border-primary/40 hover:text-foreground">
                    <ImagePlus className="size-5" />
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      multiple
                      className="hidden"
                      onChange={(e) => onFilesChange(e.target.files)}
                    />
                  </label>
                )}
              </div>
            </div>

            {formLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Kategoriya maydonlari yuklanmoqda…
              </div>
            ) : form && form.sections.length > 0 ? (
              <DynamicCategoryForm
                sections={form.sections}
                values={attributes}
                onChange={(code, value) => setAttributes((prev) => ({ ...prev, [code]: value }))}
              />
            ) : null}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <button
              type="submit"
              disabled={!canSubmit}
              className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-50"
            >
              {submitting && <Loader2 className="size-4 animate-spin" />}
              E'lonni joylashtirish
            </button>
          </form>
        )}
      </div>
    </AppShell>
  );
}
