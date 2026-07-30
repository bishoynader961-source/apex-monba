"use client";

import { createContext, useContext, useEffect, useState } from "react";

const CurrencyContext = createContext<"USD" | "EGP">("USD");

export function CurrencyProvider({ children }: { children: React.ReactNode }) {
  const [currency, setCurrency] = useState<"USD" | "EGP">("USD");

  useEffect(() => {
    const headers = new Headers();
    fetch("/api/currency", { headers })
      .then((res) => res.json())
      .then((data) => setCurrency(data.currency))
      .catch(() => {});
  }, []);

  return (
    <CurrencyContext.Provider value={currency}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency() {
  return useContext(CurrencyContext);
}
