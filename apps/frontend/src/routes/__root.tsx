import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import faviconUrl from "../assets/logo-mark.png";
import { reportLovableError } from "../lib/lovable-error-reporting";
// Side-effect import: initializes i18next before any route component renders. Previously only
// imported by routes/index.tsx, DashboardShell, and AppShell -- fragile, since a production
// build's chunk-execution order isn't guaranteed to match that import graph (unlike the dev
// server's more predictable per-request resolution), so a component like Navbar/ThemeToggle
// whose own chunk happened to execute first called useTranslation() against an uninitialized
// i18next instance and rendered raw translation keys ("hero.eyebrow") instead of text. The root
// route is the one module every other route/component provably loads after.
import "../lib/i18n";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "ActiveHome — The home & building super app" },
      {
        name: "description",
        content:
          "Buy, rent, build, furnish and book — one AI-powered ecosystem for everything related to homes and buildings, worldwide.",
      },
      { name: "author", content: "ActiveHome" },
      { property: "og:site_name", content: "ActiveHome" },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:site", content: "@ActiveHome" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", type: "image/png", href: faviconUrl },
      { rel: "apple-touch-icon", href: faviconUrl },
    ],
    scripts: [
      {
        type: "application/ld+json",
        children: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "Organization",
          name: "ActiveHome",
          url: "https://active-home.lovable.app",
          description:
            "AI-powered global super app for buying, renting, building, furnishing and booking homes.",
        }),
      },
      {
        type: "application/ld+json",
        children: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "WebSite",
          name: "ActiveHome",
          url: "https://active-home.lovable.app",
          potentialAction: {
            "@type": "SearchAction",
            target: "https://active-home.lovable.app/properties?q={search_term_string}",
            "query-input": "required name=search_term_string",
          },
        }),
      },
    ],
  }),

  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    // `lang` was hardcoded "en" while the site's actual default/primary content is Uzbek --
    // that mismatch is what makes Chrome's built-in page-translate feature think a translation
    // is needed and offer one. Accepting it lets Chrome mutate the DOM directly outside React's
    // control, which then throws real `insertBefore`/`removeChild` errors the next time React
    // reconciles that subtree (confirmed live: every one of those crashes this session traced
    // back to a `lang="en"` -> `lang="uz"` + `translated-ltr` hydration-mismatch entry
    // immediately before it). `translate="no"` + the `notranslate` meta tag are defense in depth
    // for the same reason -- the app already has its own real i18n (uz/ru/en via i18next); a
    // second, uncoordinated translation layer mutating the DOM underneath it is never wanted,
    // for real users either, not just this session's testing.
    <html lang="uz" translate="no">
      <head>
        <meta name="google" content="notranslate" />
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
      <Outlet />
    </QueryClientProvider>
  );
}
