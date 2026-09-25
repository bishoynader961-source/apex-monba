"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";

export default function SetupPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Admin form state
  const [adminName, setAdminName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Pharmacy profile state
  const [pharmacyName, setPharmacyName] = useState("");
  const [address, setAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");

  // Check setup status on load
  useEffect(() => {
    const checkSetup = async () => {
      try {
        const res = await fetch("/api/v1/setup/status");
        if (res.ok) {
          const data = await res.json();
          if (!data.setup_required) {
            router.replace("/login");
            return;
          }
        }
      } catch {
        // If setup check fails, stay on setup page
      }
    };
    checkSetup();
  }, [router]);

  // Step 2 validation
  const isStep2Valid =
    adminName.trim().length > 0 &&
    username.trim().length > 0 &&
    password.length >= 8 &&
    password === confirmPassword;

  // Step 3 validation — pharmacy details are optional (buyer may skip)
  const isStep3Valid = true;

  const handleStep1Next = () => setStep(2);
  const handleStep2Next = () => {
    if (isStep2Valid) setStep(3);
  };

  const handleStep3Submit = async () => {
    if (!isStep3Valid) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/v1/setup/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          admin_name: adminName.trim(),
          username: username.trim(),
          password,
          confirm_password: confirmPassword,
          pharmacy_name: pharmacyName.trim(),
          address: address.trim(),
          phone: phone.trim(),
          license_number: licenseNumber.trim(),
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        // 403 means setup was already completed (e.g. finished from another
        // window). Send the user to login instead of a dead-end error.
        if (res.status === 403) {
          router.replace("/login?setup=complete");
          return;
        }
        throw new Error(data.detail || "Failed to complete setup");
      }

      // Setup complete - redirect to login
      router.replace("/login?setup=complete");
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    if (step > 1) setStep(step - 1);
  };

  // Render step indicator
  const renderStepIndicator = () => (
    <div className="mb-8 flex items-center justify-center">
      {[1, 2, 3].map((s) => (
        <React.Fragment key={s}>
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-full text-sm font-medium transition-colors ${
              s < step
                ? "bg-emerald-600 text-white"
                : s === step
                ? "bg-emerald-600 text-white"
                : "bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
            }`}
          >
            {s < step ? "✓" : s}
          </div>
          {s < 3 && (
            <div
              className={`hidden w-16 h-1 mx-2 ${s < step ? "bg-emerald-600" : "bg-gray-200 dark:bg-gray-700"}`}
            />
          )}
        </React.Fragment>
      ))}
    </div>
  );

  // Step labels
  const stepLabels = [
    t("setup.welcome.heading") || "Welcome",
    t("setup.admin.heading") || "Admin Account",
    t("setup.pharmacy.heading") || "Pharmacy Profile",
  ];

  const renderStepLabels = () => (
    <div className="mb-8 flex justify-between text-xs text-gray-500 dark:text-gray-400">
      {[1, 2, 3].map((s) => (
        <div
          key={s}
          className={`w-24 text-center ${s === step ? "font-semibold text-emerald-600" : ""}`}
        >
          {stepLabels[s - 1]}
        </div>
      ))}
    </div>
  );

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md space-y-6 rounded-lg bg-white dark:bg-gray-800 p-8 shadow-lg">
        <div className="text-center">
          <span className="text-4xl">💊</span>
          <h1 className="mt-4 text-2xl font-bold text-gray-900 dark:text-white">
            {t("setup.welcome.heading")}
          </h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            {t("setup.welcome.subtext")}
          </p>
        </div>

        {renderStepIndicator()}
        {renderStepLabels()}

        {error && (
          <div role="alert" className="rounded-md bg-red-100 p-4 text-sm text-red-800 dark:bg-red-900 dark:text-red-200">
            {error}
          </div>
        )}

        {/* Step 1: Welcome */}
        {step === 1 && (
          <div className="space-y-4 text-center">
            <p className="text-gray-600 dark:text-gray-300">
              {t("setup.welcome.subtext")}
            </p>
            <button
              onClick={handleStep1Next}
              disabled={loading}
              className="w-full rounded-md bg-emerald-600 py-2 px-4 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-default disabled:opacity-70"
            >
              {t("setup.welcome.getStarted")}
            </button>
          </div>
        )}

        {/* Step 2: Create Admin Account */}
        {step === 2 && (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); handleStep2Next(); }}>
            <div>
              <label htmlFor="setup-admin-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("setup.admin.fullName")}
              </label>
              <input
                id="setup-admin-name"
                type="text"
                value={adminName}
                onChange={(e) => setAdminName(e.target.value)}
                required
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-70"
              />
            </div>
            <div>
              <label htmlFor="setup-admin-username" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("setup.admin.username")}
              </label>
              <input
                id="setup-admin-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={loading}
                minLength={3}
                pattern="[a-zA-Z0-9_\-]+"
                className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-70"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {t("setup.admin.usernameHint")}
              </p>
            </div>
            <div>
              <label htmlFor="setup-admin-password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("setup.admin.password")}
              </label>
              <div className="relative mt-1">
                <input
                  id="setup-admin-password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  disabled={loading}
                  className="block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 pr-10 text-sm text-gray-900 dark:text-gray-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-70"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                >
                  {showPassword ? "🙈" : "👁"}
                </button>
              </div>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Minimum 8 characters
              </p>
            </div>
            <div>
              <label htmlFor="setup-admin-confirm" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("setup.admin.confirmPassword")}
              </label>
              <input
                id="setup-admin-confirm"
                type={showPassword ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-70"
              />
              {confirmPassword && password !== confirmPassword && (
                <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                  {t("setup.passwordMismatch") || "Passwords do not match"}
                </p>
              )}
            </div>
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={handleBack}
                disabled={loading}
                className="flex-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 py-2 px-4 text-sm font-medium text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800 disabled:cursor-default disabled:opacity-70"
              >
                {t("common.back")}
              </button>
              <button
                type="submit"
                disabled={loading || !isStep2Valid}
                className="flex-1 rounded-md bg-emerald-600 py-2 px-4 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-default disabled:opacity-70"
              >
                {t("common.next")}
              </button>
            </div>
          </form>
        )}

        {/* Step 3: Pharmacy Profile */}
        {step === 3 && (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); handleStep3Submit(); }}>
            <p className="text-center text-sm text-gray-600 dark:text-gray-400">
              {t("setup.pharmacy.subtext")}
            </p>
            <div>
              <label htmlFor="setup-pharmacy-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("setup.pharmacy.name")}
              </label>
              <input
                id="setup-pharmacy-name"
                type="text"
                value={pharmacyName}
                onChange={(e) => setPharmacyName(e.target.value)}
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-70"
              />
            </div>
            <div>
              <label htmlFor="setup-pharmacy-address" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("setup.pharmacy.address")}
              </label>
              <textarea
                id="setup-pharmacy-address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                rows={2}
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-70"
              />
            </div>
            <div>
              <label htmlFor="setup-pharmacy-phone" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("setup.pharmacy.phone")}
              </label>
              <input
                id="setup-pharmacy-phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-70"
              />
            </div>
            <div>
              <label htmlFor="setup-pharmacy-license" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                {t("setup.pharmacy.licenseNumber")}
              </label>
              <input
                id="setup-pharmacy-license"
                type="text"
                value={licenseNumber}
                onChange={(e) => setLicenseNumber(e.target.value)}
                disabled={loading}
                className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-70"
              />
            </div>
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={handleBack}
                disabled={loading}
                className="flex-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 py-2 px-4 text-sm font-medium text-gray-700 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800 disabled:cursor-default disabled:opacity-70"
              >
                {t("common.back")}
              </button>
              <button
                type="submit"
                disabled={loading || !isStep3Valid}
                className="flex-1 rounded-md bg-emerald-600 py-2 px-4 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-default disabled:opacity-70"
              >
                {loading ? t("common.saving") : t("setup.pharmacy.finishSetup")}
              </button>
            </div>
            <button
              type="button"
              onClick={handleStep3Submit}
              disabled={loading}
              className="w-full text-center text-sm text-gray-500 dark:text-gray-400 underline hover:text-gray-700 dark:hover:text-gray-300 disabled:opacity-70"
            >
              Skip for now
            </button>
          </form>
        )}
      </div>
    </main>
  );
}