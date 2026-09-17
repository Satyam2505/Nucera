"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenuButton, useSidebar } from "@/components/ui/sidebar";
import { useAuth } from "@/lib/AuthContext";

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function AccountMenu() {
  // AccountMenu only ever renders inside AuthGate's authenticated branch,
  // so `user` is guaranteed non-null here.
  const { user, logout } = useAuth();
  const { state } = useSidebar();
  const collapsed = state === "collapsed";

  const initial = user?.email.charAt(0).toUpperCase() ?? "?";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <SidebarMenuButton
          size="lg"
          tooltip={collapsed ? user?.email : undefined}
          className="data-[state=open]:bg-sidebar-accent"
        >
          <Avatar className="h-8 w-8 rounded-full border border-[rgba(var(--accent-rgb),0.4)]">
            <AvatarFallback className="rounded-full bg-[rgba(var(--accent-rgb),0.2)] text-[var(--accent-hover)] text-xs font-semibold">
              {initial}
            </AvatarFallback>
          </Avatar>
          <span className="min-w-0 flex-1 text-left">
            <span className="block text-sm font-medium text-sidebar-foreground truncate">{user?.email}</span>
            <span className="block text-[11px] text-sidebar-foreground/70 truncate">Signed in</span>
          </span>
          <span className="text-sidebar-foreground/70 shrink-0">
            <ChevronIcon />
          </span>
        </SidebarMenuButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-64">
        <DropdownMenuLabel className="truncate font-normal text-[var(--ink)]">{user?.email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => logout()}>Log out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
