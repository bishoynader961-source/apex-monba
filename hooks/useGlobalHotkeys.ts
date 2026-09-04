import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function useGlobalHotkeys() {
  const router = useRouter();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // If the user is typing in an input, textarea, or contenteditable, we generally want to allow F-keys to work natively
      // But typically F-keys are global shortcuts in pharmacy apps. We will prevent default and navigate.
      // We should only ignore if the event is already prevented.
      if (e.defaultPrevented) return;

      let handled = false;
      switch (e.key) {
        case "F1":
          router.push("/patients");
          handled = true;
          break;
        case "F2":
          router.push("/dashboard/prescribers");
          handled = true;
          break;
        case "F3":
          router.push("/dashboard/drugs");
          handled = true;
          break;
        case "F4":
          router.push("/dashboard/insurance");
          handled = true;
          break;
        case "F5":
          // Doctor alias
          router.push("/dashboard/prescribers");
          handled = true;
          break;
        case "F6":
          router.push("/dashboard/price-codes");
          handled = true;
          break;
      }

      if (handled) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [router]);
}
