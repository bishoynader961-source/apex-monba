"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export default function PortalPage() {
  const router = useRouter();
  const [isAuthed, setIsAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    setIsAuthed(Boolean(token));
    if (token) router.replace("/dashboard");
  }, [router]);

  if (isAuthed === null) return null;

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-2xl font-bold">Pharmacy Suite Portal</h1>
      <p className="max-w-md text-muted-foreground">
        The desktop application is the recommended way to run PharmacyPro in your
        pharmacy. You can also use the web portal below.
      </p>
      {isAuthed ? (
        <Link
          href="/dashboard"
          className="rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground"
        >
          Go to Dashboard
        </Link>
      ) : (
        <Link
          href="/login"
          className="rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground"
        >
          Sign in
        </Link>
      )}
    </main>
  );
}
