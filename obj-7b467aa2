"use client";

import React from "react";
import type { Shortcut } from "@/hooks/useKeyboardShortcuts";

interface PaymentMethodToggleProps {
  paymentMethod: string;
  setPaymentMethod: (method: string) => void;
}

export const PaymentMethodToggle: React.FC<PaymentMethodToggleProps> = ({ paymentMethod, setPaymentMethod }) => {
  return (
    <div className="flex gap-2 mb-4" role="radiogroup" aria-label="Payment method">
      <button
        type="button"
        className={`px-4 py-2 rounded-md text-sm font-medium ${paymentMethod === "Cash" ? "bg-green-600 text-white" : "bg-gray-700 text-gray-300 hover:bg-gray-600"}`}
        onClick={() => setPaymentMethod("Cash")}
      >
        Cash
      </button>
      <button
        type="button"
        className={`px-4 py-2 rounded-md text-sm font-medium ${paymentMethod === "Card" ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300 hover:bg-gray-600"}`}
        onClick={() => setPaymentMethod("Card")}
      >
        Card
      </button>
    </div>
  );
};
