"use client";

import { DashboardLayout } from "@/components/DashboardLayout";

// Privacy policy content is data-driven from the actual system behavior:
// every statement here must match how the code really handles data.
// If the data flow ever changes, this page must be updated in the same change.

const SECTIONS: { title: string; body: string[] }[] = [
  {
    title: "What we collect",
    body: [
      "Pharmacy Suite runs entirely on your own computer(s). Your pharmacy's operational data — medicines, patients, prescriptions, sales, and settings — is stored in a local database file on your machine and is never transmitted to us or to any third party.",
      "When you contact support and choose to share a diagnostic report, that report contains only technical information: app version, operating system version, and a short error category code. It never contains patient data, prescription contents, passwords, or license keys.",
    ],
  },
  {
    title: "What never leaves your computer",
    body: [
      "Patient records, prescription details, and sales history remain in the local database at all times.",
      "Passwords and PINs are stored only as irreversible hashes and are never included in diagnostics, backups shared by you, or support communications.",
    ],
  },
  {
    title: "Backups",
    body: [
      "Backups are created at your direction and stay under your control. We do not receive copies of your backups and have no ability to access them.",
    ],
  },
  {
    title: "Network access",
    body: [
      "Pharmacy Suite connects to the internet only to check for software updates and to process license payments through our payment provider. These connections never include your pharmacy's operational data.",
      "The optional mobile companion app connects directly to your desktop computer over your local pharmacy network. That traffic stays on your network and does not pass through our servers.",
    ],
  },
  {
    title: "Support communications",
    body: [
      "When you email our support address, we receive only what you send: your message and any diagnostic information you explicitly attach. Support will never ask for your password or PIN.",
    ],
  },
  {
    title: "Your control",
    body: [
      "You can export or delete your data at any time from within the app. Uninstalling the application does not delete your database — you remain in control of that file.",
    ],
  },
];

export default function PrivacyPolicyPage() {
  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-2">Privacy Policy</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
          Pharmacy Suite &middot; Version 1.0.0 &middot; Effective date: September 26, 2026
        </p>

        <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-6 space-y-6">
          {SECTIONS.map((section) => (
            <section key={section.title}>
              <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-2">
                {section.title}
              </h2>
              {section.body.map((paragraph) => (
                <p
                  key={paragraph.slice(0, 32)}
                  className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed mb-2"
                >
                  {paragraph}
                </p>
              ))}
            </section>
          ))}
          <section>
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-2">Contact</h2>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              Questions about privacy:{" "}
              <span className="font-mono text-gray-800 dark:text-gray-100">pharmacypro.support@gmail.com</span>
            </p>
          </section>
        </div>
      </div>
    </DashboardLayout>
  );
}
