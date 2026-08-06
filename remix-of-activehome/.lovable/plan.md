
# ActiveHome v2 — Enterprise Platform Buildout

Continue the existing project. Same design tokens (deep-indigo OKLCH palette), same `Space Grotesk + Inter` typography, same glass / mesh / shadow utilities, same Navbar/Footer shell. Nothing in `src/styles.css` or the existing landing components gets replaced — they get reused.

Given the scope (50+ pages, real maps, full profile suite, multi-language, demo data, mock API), this is not one batch. I will ship it in **6 waves**, each fully working and previewable, so we never have a half-broken app.

---

## Wave 0 — Foundations (this turn)

Lay down the architecture every future page depends on. No new pages yet beyond plumbing.

1. **Feature-based folder structure**
   ```
   src/
     features/
       properties/   (types, api, hooks, components)
       agents/
       categories/
       map/
       profile/
       messaging/
       checkout/
       ai/
     mock/           (faker-powered demo data + latency-simulating client)
     lib/
       api-client.ts (swappable: mock today, fetch(DRF/FastAPI) tomorrow)
       format.ts     (i18n currency/date/number)
       geo.ts
     components/
       site/         (existing landing)
       layout/       (AppShell, DashboardShell, PageHeader, Section)
       ui/           (shadcn)
       data/         (PropertyCard, AgentCard, StatTile, PriceTag, FilterChip…)
       motion/       (Reveal, Magnetic, Marquee, ParallaxLayer)
       state/        (EmptyState, ErrorState, Skeletons)
   ```

2. **Mock API layer** — `@faker-js/faker` powered generators for properties, agents, agencies, reviews, messages, orders, notifications, jobs, materials, hotels. All accessed via `apiClient.properties.list({...})` so swapping to DRF/FastAPI is a one-file change.

3. **React Query + Zod** wired into the router context. Suspense-friendly `queryOptions` per resource.

4. **i18n expansion** — namespaces (`common`, `nav`, `property`, `profile`, `map`, `checkout`…) added to existing `en/uz/ru` files. `formatCurrency`, `formatDate`, RTL-aware layout class on `<html>`.

5. **Mapbox GL integration** — `MapView` component with style switcher (Streets/Satellite/Terrain/Traffic), clustered markers, geolocation, draw tools (radius + polygon via `@mapbox/mapbox-gl-draw`), heatmap layer, POI overlays (schools/hospitals/transit). Token via `VITE_MAPBOX_TOKEN` — I'll add a graceful fallback to the existing stylised map when no token is set so the preview keeps working; I'll ask you for the token after Wave 0.

6. **Global UI primitives**
   - `AppShell` (top nav for marketing routes)
   - `DashboardShell` (sidebar + topbar for authenticated routes, shadcn Sidebar)
   - `PageHeader`, `Section`, `Breadcrumbs`
   - `PageTransition` (Framer shared layout)
   - `RouteSkeleton`, `RouteError`, `RouteNotFound` defaults wired into every route

7. **Route tree skeleton** — every URL from your list created as a TanStack route with `pendingComponent`, `errorComponent`, `notFoundComponent`, and a "coming in wave N" premium placeholder (NOT a blank page — uses real PageHeader + skeleton grid so navigation already feels alive).

---

## Wave 1 — Discovery surface
Search, Search Results, Map Search, Advanced Filters, Property Details, Property Gallery, Property Comparison, Category Index + 18 category landing pages, Favorites, Recently Viewed, Saved Searches.

Real Mapbox on Map Search and Property Details. Full filter state in URL via `validateSearch`.

## Wave 2 — Identity & dashboards
Auth pages (Sign in / Sign up / Reset — UI only, Lovable Cloud later if you want real auth), User Dashboard, Buyer Dashboard, Seller Dashboard, Agent Profile, Agency Profile, Profile settings suite (Verification, Trust Score, Security/2FA, Notifications, Appearance, Connected Devices, Activity, API Tokens, Developer).

## Wave 3 — Ecosystem verticals
Construction Companies, Furniture Marketplace, Construction Materials, Interior Design, Landscape Design, Hotels, Hostels, Jobs, Service Providers. Each is a real listing + detail experience using the same `PropertyCard` family re-skinned per vertical.

## Wave 4 — Transactions & comms
Checkout, Payments, Subscriptions, Wallet, Notifications, Messages (threaded inbox), AI Assistant (chat UI wired to Lovable AI Gateway when you enable Cloud).

## Wave 5 — Content & system
About, Pricing, Blog, News, FAQ, Contact, Support Center, Settings, Privacy, Security, Verification, Admin Preview, 404, Maintenance, custom Loading screens. SEO `head()` per route.

---

## Technical notes (for later backend wiring)

- `src/lib/api-client.ts` exports a single `apiClient` whose shape mirrors your future DRF/FastAPI endpoints (`GET /properties?...`, `GET /properties/:id`, etc.). Today it returns mock data with simulated latency; flipping `VITE_API_BASE_URL` switches it to real `fetch`.
- All forms use `react-hook-form` + `zod` schemas that double as DTOs — same schema will validate API responses.
- Stack stays as-is: **TanStack Start + React 19 + Tailwind v4 + shadcn + Framer Motion + TanStack Query + Mapbox GL**. (Note: the project is TanStack Start, not Next.js — your spec mentioned Next.js, but switching frameworks would discard everything already built. I'll keep TanStack Start; the component code is identical either way.)
- No hardcoded colors anywhere — only the existing semantic tokens.

---

## What I need from you before Wave 1

1. **Mapbox public token** (`pk.…`) — required for real maps. I'll store it as `VITE_MAPBOX_TOKEN`. Without it the map gracefully falls back to the current stylised version.
2. **Lovable Cloud** — enable now so Wave 2 (auth, profile persistence, favorites, messages) and Wave 4 (AI Assistant via AI Gateway) can use real backend instead of localStorage. Recommended.
3. **Confirm framework** — stay on TanStack Start (recommended; everything already built works) vs migrate to Next.js (full restart).

Reply "go" and I'll ship Wave 0 immediately. You can answer (1)(2)(3) in the same message or after Wave 0 lands.
