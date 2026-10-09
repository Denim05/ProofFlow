import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import { Navbar } from "@/components/Navbar";
import { AuthTokenBridge } from "@/components/AuthTokenBridge";

export const metadata: Metadata = {
  title: "ProofFlow — Autonomous Incident Reconstruction",
  description:
    "AI-powered multi-document timeline reconstruction and contradiction detection engine.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="min-h-screen bg-slate-50/50 flex flex-col antialiased">
          <AuthTokenBridge />
          <Navbar />
          <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
        </body>
      </html>
    </ClerkProvider>
  );
}
