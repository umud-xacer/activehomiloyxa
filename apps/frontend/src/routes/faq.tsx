import { createFileRoute } from "@tanstack/react-router";
import { LegalPage, LegalBoxGrid } from "@/components/layout/LegalPage";

const faqEntries = [
  {
    q: "Xavfsizmi?",
    a: "Platforma e'lonlarni moderatsiya qiladi, lekin bitimdan oldin hujjatlarni mustaqil tekshirish tavsiya etiladi.",
  },
  {
    q: "E'lon bepulmi?",
    a: "Dastlabki e'lonlar limit doirasida bepul; TOP/Premium xizmatlar pullik.",
  },
  {
    q: "Usta xizmatlari qanday ishlaydi?",
    a: "Mustaqil mutaxassislar ko'rsatadi, Active Home mijoz va usta o'rtasida vositachi.",
  },
  {
    q: "To'lov qanday amalga oshiriladi?",
    a: "Pullik xizmatlar Payme/Click orqali; bitim to'lovlari tomonlar kelishuvi asosida.",
  },
  {
    q: "Xizmatdan norozi bo'lsam nima qilaman?",
    a: "\"Shikoyat\" bo'limi yoki qo'llab-quvvatlash markazi orqali murojaat qilinadi.",
  },
  {
    q: "Akkauntimni o'chira olamanmi?",
    a: "Istalgan vaqtda mumkin — o'chirilganda barcha shaxsiy ma'lumot to'liq olib tashlanadi.",
  },
];

export const Route = createFileRoute("/faq")({
  head: () => ({
    meta: [
      { title: "Tez-tez so'raladigan savollar — ActiveHome" },
      {
        name: "description",
        content:
          "ActiveHome platformasi, e'lonlar, to'lovlar va xizmatlar haqida tez-tez so'raladigan savollar.",
      },
      { property: "og:title", content: "Tez-tez so'raladigan savollar — ActiveHome" },
      {
        property: "og:description",
        content:
          "ActiveHome platformasi, e'lonlar, to'lovlar va xizmatlar haqida tez-tez so'raladigan savollar.",
      },
      { property: "og:type", content: "website" },
    ],
    scripts: [
      {
        type: "application/ld+json",
        children: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "FAQPage",
          mainEntity: faqEntries.map((e) => ({
            "@type": "Question",
            name: e.q,
            acceptedAnswer: { "@type": "Answer", text: e.a },
          })),
        }),
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <LegalPage
      eyebrow="Yordam"
      title="Tez-tez so'raladigan savollar"
      description="Eng ko'p so'raladigan savollarga javoblar."
    >
      <LegalBoxGrid items={faqEntries.map((e) => ({ title: e.q, body: e.a }))} />
    </LegalPage>
  );
}
