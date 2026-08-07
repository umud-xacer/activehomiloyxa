import { createFileRoute } from "@tanstack/react-router";
import { LegalPage, LegalSection, LegalBoxGrid } from "@/components/layout/LegalPage";

export const Route = createFileRoute("/refund")({
  head: () => ({
    meta: [
      { title: "To'lovni qaytarish — ActiveHome" },
      { name: "description", content: "To'lovlarni bekor qilish va mablag'ni qaytarish tartibi." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <LegalPage
      eyebrow="Huquqiy"
      title="To'lov va qaytarish siyosati"
      description="Pullik xizmatlar va mablag' qaytarish tartibi haqida to'liq ma'lumot."
    >
      <LegalBoxGrid
        items={[
          {
            title: "Pullik xizmatlar",
            body: "Premium e'lonlar, bannerli reklamalar, vositachilik xizmatlari, maxsus marketing paketlari.",
          },
          {
            title: "Refund tartibi",
            body: "Texnik sabab bo'lsa to'liq qaytariladi; jarayon 3–10 ish kuni ichida amalga oshiriladi.",
          },
          {
            title: "Istisno",
            body: "Foydalanuvchi xatosi yoki qoida buzilishi sababli o'chirilgan pullik e'lonlar uchun mablag' qaytarilmasligi mumkin.",
          },
          {
            title: "Nizolar",
            body: "Har bir shikoyat maxsus komissiya tomonidan individual ko'rib chiqiladi.",
          },
        ]}
      />
      <LegalSection title="Murojaat">
        <p>
          To'lov yoki qaytarish bo'yicha savollaringiz bo'lsa, qo'llab-quvvatlash markazi orqali
          murojaat qiling.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
