import type { Metadata } from "next";
import "./globals.css";
import { I18nProvider } from "@/components/I18nProvider";
import { LicenseGate } from "@/components/LicenseGate";
import { BootGuard } from "@/components/BootGuard";
import { GlobalHotkeys } from "@/components/GlobalHotkeys";
import { QueryProvider } from "./providers/QueryProvider";

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
    <html lang="en" className="dark">
      <body className="bg-[#0a0a1a] text-gray-100 antialiased">
        <QueryProvider>
          <I18nProvider>
            <BootGuard>
              <GlobalHotkeys />
              <LicenseGate>{children}</LicenseGate>
            </BootGuard>
          </I18nProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
