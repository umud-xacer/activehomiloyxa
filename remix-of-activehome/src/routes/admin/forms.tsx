import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Plus,
  Loader2,
  ClipboardList,
  CheckCircle2,
  AlertCircle,
  Trash2,
  ChevronDown,
  ChevronUp,
  Layers,
} from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import {
  adminConfigApi,
  FIELD_TYPES,
  VALIDATOR_TYPES,
  type ConfigHead,
  type FieldType,
  type FormFieldContent,
  type FormFieldOption,
  type FormSectionContent,
  type ValidatorBinding,
  type ValidatorType,
} from "@/lib/admin-config-api";
import { ApiError } from "@/lib/http";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const Route = createFileRoute("/admin/forms")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Formalar — Admin" }] }),
  component: Page,
});

const slugify = (s: string) =>
  s
    .toLowerCase()
    .trim()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const FIELD_TYPE_LABEL: Record<FieldType, string> = {
  text: "Matn",
  number: "Raqam",
  select: "Tanlov (bitta)",
  multiselect: "Tanlov (ko'p)",
  boolean: "Ha/Yo'q",
  date: "Sana",
  range: "Oraliq",
  location: "Joylashuv (xarita)",
};

const VALIDATOR_LABEL: Record<ValidatorType, string> = {
  required: "Majburiy",
  length: "Uzunlik chegarasi",
  numeric_range: "Sonli oraliq",
  pattern_safe: "Naqsh (pattern)",
  option_membership: "Tanlovlar ichida",
  image_count: "Rasmlar soni",
};

const PATTERN_KEYS = ["phone_uz", "email", "url"];

let seq = 0;
const nextId = () => `tmp_${++seq}_${Date.now()}`;

interface EditableField extends FormFieldContent {
  _key: string;
}
interface EditableSection extends FormSectionContent {
  _key: string;
}

function blankField(sectionCode: string): EditableField {
  return {
    _key: nextId(),
    code: "",
    section_code: sectionCode,
    label: { uz_latn: "" },
    field_type: "text",
    required: false,
    facet_eligible: false,
    order: 0,
    options: [],
    validators: [],
  };
}

function blankSection(): EditableSection {
  return { _key: nextId(), code: "", label: { uz_latn: "" }, order: 0 };
}

function ValidatorRow({ v, onChange, onRemove }: { v: ValidatorBinding; onChange: (v: ValidatorBinding) => void; onRemove: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-background/50 px-2.5 py-2">
      <Select value={v.validator_type} onValueChange={(t) => onChange({ validator_type: t as ValidatorType, params: {} })}>
        <SelectTrigger className="h-7 w-40 rounded-lg border-border bg-card text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {VALIDATOR_TYPES.map((t) => (
            <SelectItem key={t} value={t}>
              {VALIDATOR_LABEL[t]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {v.validator_type === "length" && (
        <>
          <input
            type="number"
            placeholder="min"
            value={(v.params.min as number) ?? ""}
            onChange={(e) => onChange({ ...v, params: { ...v.params, min: Number(e.target.value) || undefined } })}
            className="h-7 w-16 rounded-lg border border-border bg-card px-2 text-xs"
          />
          <input
            type="number"
            placeholder="max"
            value={(v.params.max as number) ?? ""}
            onChange={(e) => onChange({ ...v, params: { ...v.params, max: Number(e.target.value) || undefined } })}
            className="h-7 w-16 rounded-lg border border-border bg-card px-2 text-xs"
          />
        </>
      )}
      {v.validator_type === "numeric_range" && (
        <>
          <input
            type="number"
            placeholder="min"
            value={(v.params.min as number) ?? ""}
            onChange={(e) => onChange({ ...v, params: { ...v.params, min: Number(e.target.value) || undefined } })}
            className="h-7 w-16 rounded-lg border border-border bg-card px-2 text-xs"
          />
          <input
            type="number"
            placeholder="max"
            value={(v.params.max as number) ?? ""}
            onChange={(e) => onChange({ ...v, params: { ...v.params, max: Number(e.target.value) || undefined } })}
            className="h-7 w-16 rounded-lg border border-border bg-card px-2 text-xs"
          />
        </>
      )}
      {v.validator_type === "pattern_safe" && (
        <Select
          value={(v.params.pattern_key as string) ?? ""}
          onValueChange={(pk) => onChange({ ...v, params: { pattern_key: pk } })}
        >
          <SelectTrigger className="h-7 w-32 rounded-lg border-border bg-card text-xs">
            <SelectValue placeholder="pattern_key" />
          </SelectTrigger>
          <SelectContent>
            {PATTERN_KEYS.map((pk) => (
              <SelectItem key={pk} value={pk}>
                {pk}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <button type="button" onClick={onRemove} className="ml-auto text-muted-foreground hover:text-destructive">
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}

function FieldCard({
  field,
  sections,
  onChange,
  onRemove,
}: {
  field: EditableField;
  sections: EditableSection[];
  onChange: (f: EditableField) => void;
  onRemove: () => void;
}) {
  const [open, setOpen] = useState(true);
  const needsOptions = field.field_type === "select" || field.field_type === "multiselect";

  const setOptions = (options: FormFieldOption[]) => onChange({ ...field, options });
  const setValidators = (validators: ValidatorBinding[]) => onChange({ ...field, validators });

  return (
    <div className="rounded-xl border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3.5 py-2.5 text-left"
      >
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          {field.code || <span className="text-muted-foreground">(kod kiritilmagan)</span>}
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
            {FIELD_TYPE_LABEL[field.field_type]}
          </span>
          {field.required && <span className="text-[10px] text-destructive">majburiy</span>}
        </div>
        {open ? <ChevronUp className="size-4 text-muted-foreground" /> : <ChevronDown className="size-4 text-muted-foreground" />}
      </button>
      {open && (
        <div className="space-y-3 border-t border-border p-3.5">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-foreground/70">Kod (code) *</span>
              <input
                value={field.code}
                onChange={(e) => onChange({ ...field, code: e.target.value })}
                placeholder="bedrooms"
                className="w-full rounded-lg border border-border bg-background px-2.5 py-1.5 font-mono text-xs"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-foreground/70">Yorliq (label) *</span>
              <input
                value={field.label.uz_latn ?? ""}
                onChange={(e) => onChange({ ...field, label: { ...field.label, uz_latn: e.target.value } })}
                placeholder="Xonalar soni"
                className="w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-foreground/70">Bo'lim</span>
              <Select value={field.section_code} onValueChange={(v) => onChange({ ...field, section_code: v })}>
                <SelectTrigger className="h-8 w-full rounded-lg border-border bg-background text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {sections.map((s) => (
                    <SelectItem key={s._key} value={s.code || s._key}>
                      {s.label.uz_latn || s.code || "(nomsiz bo'lim)"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-foreground/70">Maydon turi</span>
              <Select value={field.field_type} onValueChange={(v) => onChange({ ...field, field_type: v as FieldType })}>
                <SelectTrigger className="h-8 w-full rounded-lg border-border bg-background text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FIELD_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {FIELD_TYPE_LABEL[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold text-foreground/70">Tartib</span>
              <input
                type="number"
                value={field.order}
                onChange={(e) => onChange({ ...field, order: Number(e.target.value) || 0 })}
                className="w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
              />
            </label>
            <div className="flex items-end gap-4 pb-1.5">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-foreground">
                <input
                  type="checkbox"
                  checked={field.required}
                  onChange={(e) => onChange({ ...field, required: e.target.checked })}
                  className="size-3.5 accent-primary"
                />
                Majburiy
              </label>
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-foreground">
                <input
                  type="checkbox"
                  checked={field.facet_eligible}
                  onChange={(e) => onChange({ ...field, facet_eligible: e.target.checked })}
                  className="size-3.5 accent-primary"
                />
                Qidiruv filtri bo'lishi mumkin
              </label>
            </div>
          </div>

          {needsOptions && (
            <div>
              <div className="mb-1.5 text-[11px] font-semibold text-foreground/70">Variantlar</div>
              <div className="space-y-1.5">
                {field.options.map((o, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <input
                      value={o.value}
                      onChange={(e) => {
                        const next = [...field.options];
                        next[i] = { ...o, value: e.target.value };
                        setOptions(next);
                      }}
                      placeholder="qiymat (value)"
                      className="w-28 rounded-lg border border-border bg-background px-2 py-1 font-mono text-xs"
                    />
                    <input
                      value={o.label.uz_latn ?? ""}
                      onChange={(e) => {
                        const next = [...field.options];
                        next[i] = { ...o, label: { ...o.label, uz_latn: e.target.value } };
                        setOptions(next);
                      }}
                      placeholder="ko'rinadigan nomi"
                      className="flex-1 rounded-lg border border-border bg-background px-2 py-1 text-xs"
                    />
                    <button
                      type="button"
                      onClick={() => setOptions(field.options.filter((_, idx) => idx !== i))}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setOptions([...field.options, { value: "", label: { uz_latn: "" } }])}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
                >
                  <Plus className="size-3" /> Variant qo'shish
                </button>
              </div>
            </div>
          )}

          <div>
            <div className="mb-1.5 text-[11px] font-semibold text-foreground/70">Validatsiya qoidalari</div>
            <div className="space-y-1.5">
              {field.validators.map((v, i) => (
                <ValidatorRow
                  key={i}
                  v={v}
                  onChange={(nv) => {
                    const next = [...field.validators];
                    next[i] = nv;
                    setValidators(next);
                  }}
                  onRemove={() => setValidators(field.validators.filter((_, idx) => idx !== i))}
                />
              ))}
              <button
                type="button"
                onClick={() => setValidators([...field.validators, { validator_type: "required", params: {} }])}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
              >
                <Plus className="size-3" /> Qoida qo'shish
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={onRemove}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-destructive hover:underline"
          >
            <Trash2 className="size-3" /> Maydonni o'chirish
          </button>
        </div>
      )}
    </div>
  );
}

function FormBuilder({
  initialName,
  initialCode,
  lockCode,
  initialSections,
  initialFields,
  onSave,
  saving,
  saveError,
  saveLabel,
}: {
  initialName: string;
  initialCode: string;
  lockCode: boolean;
  initialSections: EditableSection[];
  initialFields: EditableField[];
  onSave: (input: { name: string; code: string; sections: FormSectionContent[]; fields: FormFieldContent[] }) => void;
  saving: boolean;
  saveError: string | null;
  saveLabel: string;
}) {
  const [name, setName] = useState(initialName);
  const [code, setCode] = useState(initialCode);
  const [codeEdited, setCodeEdited] = useState(lockCode);
  const [sections, setSections] = useState<EditableSection[]>(initialSections.length ? initialSections : [blankSection()]);
  const [fields, setFields] = useState<EditableField[]>(initialFields);
  const [localError, setLocalError] = useState<string | null>(null);

  const setSection = (key: string, patch: Partial<EditableSection>) =>
    setSections((prev) => prev.map((s) => (s._key === key ? { ...s, ...patch } : s)));

  const removeSection = (key: string) => {
    const sec = sections.find((s) => s._key === key);
    if (sec && fields.some((f) => f.section_code === sec.code)) {
      setLocalError("Bu bo'limda hali maydonlar bor — avval ularni ko'chiring yoki o'chiring.");
      return;
    }
    setSections((prev) => prev.filter((s) => s._key !== key));
  };

  const submit = () => {
    setLocalError(null);
    if (!name.trim()) return setLocalError("Forma nomini kiriting");
    if (sections.some((s) => !s.code.trim())) return setLocalError("Har bir bo'lim uchun kod kiriting");
    if (fields.length === 0) return setLocalError("Kamida bitta maydon qo'shing");
    if (fields.some((f) => !f.code.trim())) return setLocalError("Har bir maydon uchun kod kiriting");
    const codes = fields.map((f) => f.code);
    if (new Set(codes).size !== codes.length) return setLocalError("Maydon kodlari takrorlanmasligi kerak");
    onSave({
      name,
      code: code || slugify(name),
      sections: sections.map(({ _key: _k, ...s }) => s),
      fields: fields.map(({ _key: _k, ...f }) => f),
    });
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Forma nomi *</span>
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!codeEdited) setCode(slugify(e.target.value));
            }}
            placeholder="Masalan: Ko'chmas mulk formasi"
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Kod *{lockCode && " (o'zgarmas)"}</span>
          <input
            value={code}
            disabled={lockCode}
            onChange={(e) => {
              setCodeEdited(true);
              setCode(slugify(e.target.value));
            }}
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 font-mono text-sm disabled:opacity-60"
          />
        </label>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Layers className="size-4 text-primary" /> Bo'limlar
        </div>
        <div className="space-y-2">
          {sections.map((s) => (
            <div key={s._key} className="flex items-center gap-1.5">
              <input
                value={s.code}
                onChange={(e) => setSection(s._key, { code: slugify(e.target.value) })}
                placeholder="kod"
                className="w-28 rounded-lg border border-border bg-background px-2.5 py-1.5 font-mono text-xs"
              />
              <input
                value={s.label.uz_latn ?? ""}
                onChange={(e) => setSection(s._key, { label: { ...s.label, uz_latn: e.target.value } })}
                placeholder="Nomi (masalan: Tafsilotlar)"
                className="flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
              />
              <input
                type="number"
                value={s.order}
                onChange={(e) => setSection(s._key, { order: Number(e.target.value) || 0 })}
                className="w-16 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
              />
              <button type="button" onClick={() => removeSection(s._key)} className="text-muted-foreground hover:text-destructive">
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setSections((prev) => [...prev, blankSection()])}
            className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
          >
            <Plus className="size-3.5" /> Bo'lim qo'shish
          </button>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <ClipboardList className="size-4 text-primary" /> Maydonlar ({fields.length})
        </div>
        <div className="space-y-2.5">
          {fields.map((f) => (
            <FieldCard
              key={f._key}
              field={f}
              sections={sections}
              onChange={(nf) => setFields((prev) => prev.map((x) => (x._key === f._key ? nf : x)))}
              onRemove={() => setFields((prev) => prev.filter((x) => x._key !== f._key))}
            />
          ))}
          <button
            type="button"
            onClick={() => setFields((prev) => [...prev, blankField(sections[0]?.code ?? "")])}
            disabled={sections.length === 0}
            className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline disabled:opacity-50"
          >
            <Plus className="size-3.5" /> Maydon qo'shish
          </button>
        </div>
      </div>

      {(localError || saveError) && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-xs text-destructive">
          <AlertCircle className="size-4 shrink-0" /> {localError ?? saveError}
        </div>
      )}

      <button
        type="button"
        onClick={submit}
        disabled={saving}
        className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-50"
      >
        {saving ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
        {saveLabel}
      </button>
    </div>
  );
}

function CreatePanel({ onDone }: { onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const mutation = useMutation({
    mutationFn: (input: { name: string; code: string; sections: FormSectionContent[]; fields: FormFieldContent[] }) =>
      adminConfigApi.createFormDefinition(input),
    onSuccess: () => {
      setOk(true);
      onDone();
      setTimeout(() => setOk(false), 2500);
    },
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Yaratib bo'lmadi"),
  });

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Plus className="size-4 text-primary" /> Yangi forma
      </div>
      <FormBuilder
        initialName=""
        initialCode=""
        lockCode={false}
        initialSections={[]}
        initialFields={[]}
        onSave={(input) => {
          setError(null);
          mutation.mutate(input);
        }}
        saving={mutation.isPending}
        saveError={error}
        saveLabel="Yaratish va nashr qilish"
      />
      {ok && (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
          <CheckCircle2 className="size-4" /> Forma yaratildi va nashr qilindi
        </div>
      )}
    </div>
  );
}

function EditPanel({ head, onDone }: { head: ConfigHead; onDone: () => void }) {
  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["admin", "form-def-version", head.id, head.currentVersionId],
    queryFn: () => adminConfigApi.getVersion("form-definition", head.id, head.currentVersionId as string),
    enabled: !!head.currentVersionId,
  });
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const mutation = useMutation({
    mutationFn: (input: { name: string; sections: FormSectionContent[]; fields: FormFieldContent[] }) => {
      if (!data) throw new Error("Ma'lumot yuklanmadi");
      return adminConfigApi.updateFormDefinition(head.id, data.definition, input);
    },
    onSuccess: () => {
      setOk(true);
      onDone();
      setTimeout(() => setOk(false), 2500);
    },
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Saqlab bo'lmadi"),
  });

  if (isLoading) return <div className="h-40 animate-pulse rounded-2xl bg-muted" />;
  if (loadError || !data)
    return (
      <div className="text-xs text-destructive">
        {loadError instanceof ApiError ? loadError.problem.detail ?? loadError.problem.title : "Yuklanmadi"}
      </div>
    );

  const def = data.definition as {
    descriptor?: { name?: { uz_latn?: string } };
    sections?: FormSectionContent[];
    fields?: FormFieldContent[];
  };

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <FormBuilder
        initialName={def.descriptor?.name?.uz_latn ?? ""}
        initialCode={head.code}
        lockCode
        initialSections={(def.sections ?? []).map((s) => ({ ...s, _key: nextId() }))}
        initialFields={(def.fields ?? []).map((f) => ({ ...f, _key: nextId() }))}
        onSave={(input) => {
          setError(null);
          mutation.mutate({ name: input.name, sections: input.sections, fields: input.fields });
        }}
        saving={mutation.isPending}
        saveError={error}
        saveLabel="O'zgarishlarni saqlash"
      />
      {ok && (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
          <CheckCircle2 className="size-4" /> Saqlandi va nashr qilindi
        </div>
      )}
    </div>
  );
}

function Page() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"list" | "create">("list");
  const [editingHeadId, setEditingHeadId] = useState<string | null>(null);

  const { data: heads = [], isLoading } = useQuery({
    queryKey: ["admin", "config-heads", "form-definition"],
    queryFn: () => adminConfigApi.listHeads("form-definition"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "config-heads", "form-definition"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "form-def-version"] });
    setMode("list");
    setEditingHeadId(null);
  };

  const editingHead = heads.find((h) => h.id === editingHeadId);

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-foreground">Formalar</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Har bir kategoriyaga bog'langan dinamik forma — maydonlar, turlar va validatsiya qoidalari.
          </p>
        </div>
        {mode === "list" && !editingHeadId && (
          <button
            onClick={() => setMode("create")}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow"
          >
            <Plus className="size-4" /> Yangi forma
          </button>
        )}
      </div>

      {mode === "create" ? (
        <>
          <button onClick={() => setMode("list")} className="mb-4 text-xs font-semibold text-muted-foreground hover:text-foreground">
            ← Ro'yxatga qaytish
          </button>
          <CreatePanel onDone={refresh} />
        </>
      ) : editingHead ? (
        <>
          <button onClick={() => setEditingHeadId(null)} className="mb-4 text-xs font-semibold text-muted-foreground hover:text-foreground">
            ← Ro'yxatga qaytish
          </button>
          <EditPanel head={editingHead} onDone={refresh} />
        </>
      ) : isLoading ? (
        <div className="h-64 animate-pulse rounded-2xl bg-muted" />
      ) : heads.length === 0 ? (
        <EmptyState icon={ClipboardList} title="Forma yo'q" description="Yuqoridagi tugma orqali birinchi formani yarating." />
      ) : (
        <div className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card">
          {heads.map((h) => (
            <button
              key={h.id}
              onClick={() => setEditingHeadId(h.id)}
              className="flex w-full items-center justify-between px-4 py-3.5 text-left hover:bg-muted/30"
            >
              <div>
                <div className="text-sm font-medium text-foreground">{h.code}</div>
                <div className="text-[11px] text-muted-foreground">{h.businessOwner}</div>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  h.status === "PUBLISHED" ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"
                }`}
              >
                {h.status}
              </span>
            </button>
          ))}
        </div>
      )}
    </AdminShell>
  );
}
