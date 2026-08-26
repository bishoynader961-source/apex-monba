"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";

import { useLicenseGate } from "@/hooks/useLicenseGate";
import { LoadingSplash } from "@/components/LoadingSplash";

export function LicenseGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { shouldGate, loading, licensed } = useLicenseGate();

  useEffect(() => {
    if (shouldGate && !loading && !licensed) {
      router.replace("/license");
    }
  }, [shouldGate, loading, licensed, router]);

  if (shouldGate && loading) return <LoadingSplash />;
  if (shouldGate && !licensed) return null;
  return <>{children}</>;
}
