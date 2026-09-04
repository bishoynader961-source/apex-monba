"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { useLicenseGate } from "@/hooks/useLicenseGate";
import { LoadingSplash } from "@/components/LoadingSplash";

export function LicenseGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { shouldGate, loading, licensed } = useLicenseGate();

  const isOnLicensePage = pathname.startsWith("/license");

  useEffect(() => {
    if (shouldGate && !loading && !licensed && !isOnLicensePage) {
      router.replace("/license");
    }
  }, [shouldGate, loading, licensed, router, isOnLicensePage]);

  if (shouldGate && loading) return <LoadingSplash />;
  return <>{children}</>;
}
