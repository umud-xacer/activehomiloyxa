import { createFileRoute } from "@tanstack/react-router";
import { LegalPage, LegalSection, LegalList } from "@/components/layout/LegalPage";

export const Route = createFileRoute("/privacy")({
  head: () => ({
    meta: [
      { title: "Maxfiylik siyosati — ActiveHome" },
      {
        name: "description",
        content: "ActiveHome shaxsiy ma'lumotlaringizni qanday yig'adi va ishlatadi.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <LegalPage
      eyebrow="Huquqiy"
      title="Maxfiylik siyosati"
      updated="Oxirgi yangilanish: 15-fevral, 2026"
    >
      <LegalSection title="Yig'iladigan ma'lumotlar">
        <LegalList
          items={[
            "Ism-familiya",
            "Telefon raqami / elektron pochta",
            "Joylashuv",
            "E'lon mazmuni va rasmlar",
            "Texnik ma'lumotlar (IP manzil, brauzer turi)",
          ]}
        />
      </LegalSection>

      <LegalSection title="Foydalanish maqsadi">
        <LegalList
          items={[
            "E'lonlarni boshqarish",
            "Foydalanuvchi bilan aloqa",
            "Xizmat sifati va xavfsizlikni ta'minlash",
            "Marketing — faqat sizning roziligingiz bilan",
          ]}
        />
      </LegalSection>

      <LegalSection title="Ma'lumotlarni uzatish">
        <p>
          Ma'lumotlaringiz faqat ichki tizim doirasida yoki qonuniy talab bo'yicha uzatiladi —
          uchinchi shaxslarga sotilmaydi.
        </p>
      </LegalSection>

      <LegalSection title="Sizning huquqlaringiz">
        <LegalList
          items={[
            "O'z ma'lumotlaringizga kirish",
            "Ma'lumotlarni yangilash",
            "E'lon yoki hisobni o'chirishni so'rash",
          ]}
        />
      </LegalSection>
    </LegalPage>
  );
}
