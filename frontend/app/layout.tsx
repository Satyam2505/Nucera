import "./globals.css";
import type { ReactNode } from "react";

import { AppStateProvider } from "@/lib/AppStateContext";

export const metadata = {
  title: "EduPilot AI",
  description: "Personal adaptive tutor",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full bg-[#E6D8C1] text-[#222222] antialiased">
        <AppStateProvider>{children}</AppStateProvider>
      </body>
    </html>
  );
}
