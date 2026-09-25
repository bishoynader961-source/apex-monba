"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.push("/pos");
  }, [router]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center">
      <header className="w-full flex items-center justify-between px-6 py-4 absolute top-0">
        <span className="font-bold text-lg">PharmacyPro</span>
        <a
          href="/portal"
          className="px-4 py-2 text-sm font-medium border border-border rounded-lg hover:bg-accent transition"
        >
          Download App
        </a>
      </header>
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">PharmacyPro</h1>
        <p className="text-lg text-muted-foreground mb-8">
          Pharmacy Management Suite
        </p>
        <p className="text-muted-foreground">Redirecting to POS...</p>
      </div>
    </main>
  );
}
