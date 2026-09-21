import type { Metadata } from "next";
import "./globals.css";
import { ResearchUseWarning } from "@/components/ResearchUseWarning";
import { SiteNav } from "@/components/SiteNav";

export const metadata: Metadata = {
  title: "TrialLens Lite",
  description:
    "A clinical-trial literature assistant that searches ClinicalTrials.gov and PubMed, and answers questions using only retrieved, cited evidence.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <ResearchUseWarning />
        <SiteNav />
        {children}
      </body>
    </html>
  );
}
