import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import {
  Home,
  Hammer,
  ShoppingBag,
  Mountain,
  ShieldCheck,
  MessageCircle,
  Wallet,
  UserRound,
  Building2,
  TrendingUp,
  CheckCircle2,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { LegalBoxGrid } from "@/components/layout/LegalPage";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "ActiveHome haqida — missiya va ekotizim" },
      {
        name: "description",
        content:
          "ActiveHome — uy, qurilish, qurilish mollari va dam olish maskanlarini birlashtirgan yagona platforma.",
      },
    ],
  }),
  component: Page,
});

const CAPABILITIES = [
  {
    Icon: Home,
    title: "Ko'chmas mulk",
    desc: "Kvartira, uy, tijorat ob'ekti va yer uchastkalarini sotib oling yoki ijaraga oling — AI baholash bilan.",
  },
  {
    Icon: Hammer,
    title: "Qurilish",
    desc: "Tasdiqlangan quruvchilar, arxitektorlar va pudratchilar bilan to'g'ridan-to'g'ri bog'laning.",
  },
  {
    Icon: ShoppingBag,
    title: "Qurilish mollari",
    desc: "Mixdan sement, g'isht, bo'yoq va armaturagacha — yetkazib beruvchilardan birma-bir buyurtma.",
  },
  {
    Icon: Mountain,
    title: "Dam olish maskanlari",
    desc: "Tog', ko'l va issiq buloq bo'yidagi turbazalarni toping va telefon orqali bron qiling.",
  },
  {
    Icon: ShieldCheck,
    title: "Tasdiqlash tizimi",
    desc: "Kompaniyalar va e'lonlar uchun ishonch nishoni — kim bilan ish yuritayotganingizni bilib turing.",
  },
  {
    Icon: MessageCircle,
    title: "To'g'ridan-to'g'ri muloqot",
    desc: "Sotuvchi, usta yoki mehmonxona bilan ilova ichidan xabar almashing.",
  },
];

const ROLES = [
  {
    Icon: UserRound,
    title: "Jismoniy shaxs",
    desc: "Uy qidirasizmi, ijaraga olmoqchimisiz yoki xizmat izlayapsizmi — oddiy anketa bilan ro'yxatdan o'ting.",
  },
  {
    Icon: Building2,
    title: "Yuridik shaxs — Ishlab chiqaruvchi",
    desc: "Qurilish kompaniyasi yoki ishlab chiqaruvchimisiz — biznes profilingizni yarating, e'lon joylang, tasdiqlash nishonini oling.",
  },
  {
    Icon: TrendingUp,
    title: "Investor",
    desc: "Qurilish loyihalariga mablag' kiriting va portfelingizni kuzatib boring.",
  },
];

const STEPS = [
  {
    n: "01",
    title: "Ro'yxatdan o'ting",
    desc: "Rolingizni tanlang (jismoniy/yuridik shaxs/investor) va qisqa anketa to'ldiring.",
  },
  {
    n: "02",
    title: "Admin tekshiradi",
    desc: "Xavfsizlik uchun har bir yangi akkauntni jamoamiz qo'lda ko'rib chiqadi — bu odatda tez orada bajariladi.",
  },
  {
    n: "03",
    title: "Ishga tushing",
    desc: "Tasdiqlangach, rolingizga mos panel ochiladi: e'lon joylang, xarid qiling yoki bron qiling.",
  },
];

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="ActiveHome haqida"
        title="Uy va qurilish uchun yagona ekotizim"
        description="Avval bir necha alohida ilova va vositachi orqali hal qilinadigan ishlarni — bitta ishonchli platformada birlashtiramiz."
      />

      <div className="mx-auto max-w-5xl px-4 pb-24 lg:px-8">
        {/* Mission */}
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="rounded-3xl border border-border bg-card p-8 shadow-soft"
        >
          <h2 className="font-display text-2xl font-semibold">Missiyamiz</h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            O'zbekistonda uy va bino bilan bog'liq har bir jarayon — sotib olish, ijara, qurilish,
            materiallar, jihozlash va dam olish — bir-biridan ajralgan holda, ko'plab vositachilar
            orqali amalga oshiriladi. ActiveHome bularning barchasini <b>bitta</b> ishonchli, sun'iy
            intellekt yordamida ishlaydigan platformaga jamlaydi: xaridor ham, quruvchi ham, ishlab
            chiqaruvchi ham, investor ham — bir joyda.
          </p>
        </motion.section>

        {/* Company services -- O'zbekistonda ko'chmas mulk bozorining ishonchli hamkori */}
        <section className="mt-16">
          <h2 className="font-display text-2xl font-semibold">Kompaniya xizmatlari</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            O'zbekistonda ko'chmas mulk bozorining ishonchli hamkori.
          </p>
          <div className="mt-6">
            <LegalBoxGrid
              items={[
                {
                  title: "Ipoteka va kredit",
                  body: "Ipoteka rasmiylashtirish va mikroqarz masalalarida yordam.",
                },
                {
                  title: "Oldi-sotdi",
                  body: "Uy sotib olish va sotish jarayonini tezkor va xavfsiz amalga oshirish.",
                },
                {
                  title: "Noturar binolar",
                  body: "Tijorat va noturar obyektlar bo'yicha keng qamrovli xizmatlar.",
                },
                {
                  title: "Shaxsiy qidiruv",
                  body: "Byudjet va talabga qarab eng mos uylarni topish.",
                },
                {
                  title: "Noldan ta'mirlash",
                  body: "Kalit topshirishgacha bo'lgan to'liq ta'mirlash xizmati.",
                },
                {
                  title: "Tezkor yechimlar",
                  body: "Uyini tezda sotmoqchi bo'lganlar uchun tayyor yechimlar.",
                },
              ]}
            />
          </div>
        </section>

        {/* Capabilities */}
        <section className="mt-16">
          <h2 className="font-display text-2xl font-semibold">Platformada nima qila olasiz</h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CAPABILITIES.map((c, i) => (
              <motion.div
                key={c.title}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-60px" }}
                transition={{ delay: i * 0.05 }}
                className="rounded-2xl border border-border bg-card p-5 shadow-soft"
              >
                <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <c.Icon className="size-5" />
                </div>
                <h3 className="font-display mt-3 text-base font-semibold">{c.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{c.desc}</p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section className="mt-16">
          <h2 className="font-display text-2xl font-semibold">Qanday ishlaydi</h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.n} className="rounded-2xl border border-border bg-card p-5 shadow-soft">
                <div className="font-display text-3xl font-semibold text-primary/40">{s.n}</div>
                <h3 className="font-display mt-2 text-base font-semibold">{s.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{s.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Roles */}
        <section className="mt-16">
          <h2 className="font-display text-2xl font-semibold">Uchta foydalanuvchi turi</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Ro'yxatdan o'tishda tanlagan rolingizga qarab, sizga alohida ishlab chiqilgan panel
            ochiladi.
          </p>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            {ROLES.map((r) => (
              <div
                key={r.title}
                className="rounded-2xl border border-border bg-card p-5 shadow-soft"
              >
                <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <r.Icon className="size-5" />
                </div>
                <h3 className="font-display mt-3 text-base font-semibold">{r.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{r.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Trust */}
        <section className="mt-16 rounded-3xl border border-border bg-card p-8 shadow-soft">
          <div className="flex items-start gap-4">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-success/10 text-success">
              <ShieldCheck className="size-6" />
            </div>
            <div>
              <h2 className="font-display text-xl font-semibold">Ishonch va xavfsizlik</h2>
              <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                {[
                  "Har bir yangi akkaunt admin tomonidan qo'lda tekshiriladi",
                  "Kompaniyalar uchun alohida to'lovli tasdiqlash nishoni (Verified badge)",
                  "E'lonlar va profillar moderatsiya tizimi orqali nazorat qilinadi",
                  "To'lovlar va obunalar shaffof, bekor qilish imkoni mavjud",
                ].map((t) => (
                  <li key={t} className="flex items-start gap-2">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> {t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="mt-16 flex flex-col items-center gap-4 rounded-3xl bg-primary px-8 py-12 text-center text-primary-foreground">
          <Wallet className="size-8 opacity-80" />
          <h2 className="font-display text-2xl font-semibold">Bugun boshlang</h2>
          <p className="max-w-md text-sm opacity-80">
            Rolingizni tanlang, qisqa anketa to'ldiring va ActiveHome ekotizimiga qo'shiling.
          </p>
          <Link
            to="/auth/sign-up"
            className="rounded-full bg-white px-6 py-2.5 text-sm font-semibold text-primary shadow-soft hover:shadow-glow"
          >
            Ro'yxatdan o'tish
          </Link>
        </section>
      </div>
    </AppShell>
  );
}
