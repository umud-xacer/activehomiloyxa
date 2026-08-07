import { createFileRoute } from "@tanstack/react-router";
import { LegalPage, LegalSection, LegalBadges } from "@/components/layout/LegalPage";

export const Route = createFileRoute("/rules")({
  head: () => ({
    meta: [
      { title: "E'lon qoidalari — ActiveHome" },
      {
        name: "description",
        content: "E'lon joylashtirish, tahrirlash va nazorat qilish tartib-qoidalari.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <LegalPage
      eyebrow="Qoidalar"
      title="E'lon qoidalari"
      description="Sifatli va ishonchli muhit yaratish uchun belgilangan tartib."
    >
      <LegalSection title="Taqiqlanadi">
        <LegalBadges
          items={["Soxta e'lonlar", "Hujjatsiz obyektlar", "Spam e'lonlar", "Yolg'on narxlar"]}
        />
      </LegalSection>

      <LegalSection title="Surat talablari">
        <p>
          Rasmlar haqiqiy va e'lon qilinayotgan obyektga tegishli, yuqori sifatli bo'lishi kerak.
          Internetdan olingan, ruxsatsiz rasmlar aniqlangan zahoti e'londan olib tashlanadi.
        </p>
      </LegalSection>

      <LegalSection title="Moderatsiya">
        <p>
          Barcha e'lonlar platforma tomonidan tekshiriladi. Talabga javob bermaydigan e'lonlar
          ogohlantirishsiz o'chirilishi mumkin.
        </p>
      </LegalSection>
    </LegalPage>
  );
}
