import type { Metadata } from "next";
import "./globals.css";
import { I18nProvider } from "@/components/I18nProvider";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { LicenseGate } from "@/components/LicenseGate";
import { BootGuard } from "@/components/BootGuard";

export const metadata: Metadata = {
  title: "PharmacyPro",
  description: "Pharmacy management SaaS application",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <I18nProvider>
          <BootGuard>
            <header className="flex items-center justify-end border-b border-gray-200 bg-white px-4 py-2 dark:border-gray-700 dark:bg-gray-800">
              <LanguageSwitcher />
            </header>
            <LicenseGate>{children}</LicenseGate>
          </BootGuard>
        </I18nProvider>
      </body>
    </html>
  );
}
