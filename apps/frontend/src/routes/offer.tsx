import { createFileRoute } from "@tanstack/react-router";
import { LegalPage, LegalSection, LegalList } from "@/components/layout/LegalPage";

export const Route = createFileRoute("/offer")({
  head: () => ({
    meta: [
      { title: "Ommaviy oferta — ActiveHome" },
      {
        name: "description",
        content: "Xizmatlardan foydalanish yuzasidan ommaviy taklif (oferta) shartlari.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <LegalPage eyebrow="Huquqiy" title="Ommaviy oferta" updated="Versiya 1.0.2, 2024">
      <LegalSection title="Platforma maqomi">
        <p>
          Active Home — axborot almashinuvi uchun onlayn maydon, tovar yoki xizmatlarning bevosita
          sotuvchisi emas.
        </p>
      </LegalSection>

      <LegalSection title="Bitimlar va mas'uliyat">
        <LegalList
          items={[
            "Active Home bitimning tomoni hisoblanmaydi",
            "Narx va muddatlar tomonlar o'rtasida mustaqil belgilanadi",
            "Nizolar O'zbekiston Respublikasi qonunchiligi asosida ko'rib chiqiladi",
          ]}
        />
      </LegalSection>

      <LegalSection title="Foydalanuvchi majburiyatlari">
        <LegalList
          items={[
            "Faqat haqiqiy ma'lumot joylashtirish",
            "Noqonuniy faoliyat bilan shug'ullanmaslik",
            "Boshqa foydalanuvchilar huquqini buzmaslik",
          ]}
        />
      </LegalSection>

      <LegalSection title="Aloqa">
        <p>
          Savollaringiz bo'lsa:{" "}
          <a
            href="mailto:support@activehome.uz"
            className="font-medium text-primary hover:underline"
          >
            support@activehome.uz
          </a>
        </p>
      </LegalSection>
    </LegalPage>
  );
}
