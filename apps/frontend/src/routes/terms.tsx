import { createFileRoute } from "@tanstack/react-router";
import { LegalPage, LegalSection, LegalList } from "@/components/layout/LegalPage";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [
      { title: "Foydalanish shartlari — ActiveHome" },
      {
        name: "description",
        content: "ActiveHome platformasidan foydalanish shartlari va qoidalari.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <LegalPage
      eyebrow="Huquqiy"
      title="Foydalanish shartlari"
      description="Active Home — qurilish va ko'chmas mulk sohasidagi ko'p tarmoqli holding kompaniya."
    >
      <LegalSection title="Yo'nalishlarimiz">
        <LegalList
          items={[
            "Ko'chmas mulk savdosi",
            "Qurilish va ta'mirlash",
            "Usta va texnik xizmatlar",
            "Qurilish materiallari savdosi",
            "Ipoteka maslahatlari",
            "Moliyaviy yo'naltirish",
          ]}
        />
      </LegalSection>

      <LegalSection title="Asosiy xizmatlar">
        <LegalList
          items={[
            "E'lon joylashtirish va sotish",
            "Vositachilik / konsalting",
            "Ixtisoslashgan usta xizmatlari",
            "Qurilish materiallari onlayn katalogi",
          ]}
        />
      </LegalSection>

      <LegalSection title="Muhim ogohlantirish">
        <p>
          Veb-sayt orqali kredit yoki moliyaviy shartnomalar to'g'ridan-to'g'ri rasmiylashtirilmaydi
          — bu jarayonlar hamkor banklar orqali amalga oshiriladi.
        </p>
      </LegalSection>

      <LegalSection title="Rozilik">
        <p>Saytdan foydalanish orqali foydalanuvchi ushbu shartlarga to'liq rozilik bildiradi.</p>
      </LegalSection>
    </LegalPage>
  );
}
