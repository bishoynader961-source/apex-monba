import { PricingCard } from "@/components/PricingCard";

export default function Home() {
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
      <PricingCard />
    </main>
  );
}
