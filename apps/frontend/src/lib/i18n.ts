import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "@/locales/en.json";
import uz from "@/locales/uz.json";
import ru from "@/locales/ru.json";

const DEFAULT_LNG = "uz";

if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    resources: {
      en: { translation: en },
      uz: { translation: uz },
      ru: { translation: ru },
    },
    // Always initialize with the same language on server and client to avoid
    // hydration mismatches. The stored preference is applied after hydration.
    lng: DEFAULT_LNG,
    fallbackLng: DEFAULT_LNG,
    supportedLngs: ["uz", "en", "ru"],
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });
}

// Uzbek is the primary language. We only honor an explicit user override
// stored after they interact with the language switcher.
if (typeof window !== "undefined") {
  try {
    const stored = window.localStorage.getItem("i18nextLng");
    const userPicked = window.localStorage.getItem("i18nextUserPicked") === "1";
    if (userPicked && stored && ["uz", "en", "ru"].includes(stored) && stored !== i18n.language) {
      queueMicrotask(() => {
        i18n.changeLanguage(stored);
      });
    } else {
      // Clear any legacy stored value so uz stays default across reloads.
      window.localStorage.setItem("i18nextLng", DEFAULT_LNG);
    }
    i18n.on("languageChanged", (lng) => {
      try {
        window.localStorage.setItem("i18nextLng", lng);
        window.localStorage.setItem("i18nextUserPicked", "1");
      } catch {
        /* ignore */
      }
    });
  } catch {
    /* ignore */
  }
}

export default i18n;
