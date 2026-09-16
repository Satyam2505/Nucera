import "./globals.css";
import type { ReactNode } from "react";

import { AppStateProvider } from "@/lib/AppStateContext";

export const metadata = {
  title: "EduPilot AI",
  description: "Personal adaptive tutor",
};

// Runs before hydration so the correct theme is already on <html> for the
// very first paint — otherwise a dark-mode visitor sees a flash of the
// light theme while React boots.
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('edupilot-theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.setAttribute('data-theme','dark');}else if(t==='light'){document.documentElement.setAttribute('data-theme','light');}}catch(e){}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="h-full bg-[var(--bg-page)] text-[var(--ink)] antialiased">
        <AppStateProvider>{children}</AppStateProvider>
      </body>
    </html>
  );
}
