import "./globals.css";
import type { ReactNode } from "react";

import AuthGate from "@/components/AuthGate";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/AuthContext";

export const metadata = {
  title: "Nucera",
  description: "Personal adaptive tutor",
  icons: {
    icon: "/nucera-mark.svg",
  },
};

// Runs before hydration so the correct theme is already on <html> for the
// very first paint — otherwise a dark-mode visitor sees a flash of the
// light theme while React boots.
const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('nucera-theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.setAttribute('data-theme','dark');}else if(t==='light'){document.documentElement.setAttribute('data-theme','light');}}catch(e){}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="h-full bg-[var(--bg-page)] text-[var(--ink)] antialiased">
        <AuthProvider>
          <TooltipProvider>
            <AuthGate>{children}</AuthGate>
          </TooltipProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
