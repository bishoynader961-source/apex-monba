import type { Metadata } from "next";
import "./globals.css";
import { I18nProvider } from "@/components/I18nProvider";
import { BootGuard } from "@/components/BootGuard";
import { GlobalHotkeys } from "@/components/GlobalHotkeys";
import { SessionTimerProvider } from "@/hooks/useSessionTimer";
import { AlertProvider } from "@/components/AlertProvider";
import { RegionProvider } from "@/components/RegionProvider";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { VersionProvider } from "@/components/VersionProvider";
import { QueryProvider } from "./providers/QueryProvider";
import { PermissionRefreshProvider } from "@/hooks/usePermissionRefresh";

export const metadata: Metadata = {
  title: "Pharmacy Suite",
  description: "Pharmacy management application",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var theme = localStorage.getItem('theme');
                  if (theme !== 'light' && theme !== 'dark') {
                    theme = 'light'; // Default: light mode. Users can switch in settings.
                    localStorage.setItem('theme', 'light');
                  }
                  document.documentElement.classList.remove('light', 'dark');
                  document.documentElement.classList.add(theme);
                  var b = parseFloat(localStorage.getItem('ui-brightness') || '1');
                  if (!isNaN(b) && b >= 0.8 && b <= 1.2) {
                    document.documentElement.style.setProperty('--user-brightness', String(b));
                  }
                  // Apply the saved locale direction before first paint so an
                  // Arabic install never flashes an LTR layout. RTL locales:
                  // ar is the only one shipped today.
                  var rtl = ['ar'];
                  var locale = localStorage.getItem('locale');
                  if (locale) {
                    document.documentElement.lang = locale;
                    document.documentElement.dir = rtl.indexOf(locale) !== -1 ? 'rtl' : 'ltr';
                  }
                } catch (e) {
                  document.documentElement.classList.add('light');
                }
              })();
            `,
          }}
        />
      </head>
      <body className="antialiased bg-background text-textMain">
        <QueryProvider>
          <I18nProvider>
            <BootGuard>
              <GlobalHotkeys />
              <SessionTimerProvider>
                <RegionProvider>
                  <AlertProvider>
                    <ErrorBoundary>
                      <VersionProvider>
                        <PermissionRefreshProvider>
                          {children}
                        </PermissionRefreshProvider>
                      </VersionProvider>
                    </ErrorBoundary>
                  </AlertProvider>
                </RegionProvider>
              </SessionTimerProvider>
            </BootGuard>
          </I18nProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
