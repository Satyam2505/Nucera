"use client";

import Link from "next/link";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Input } from "@/components/ui/input";
import type { Course } from "@/lib/api";
import { badgeColorFor, courseHref } from "@/lib/courses";

import AccountMenu from "./AccountMenu";
import ThemeToggle from "./ThemeToggle";

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function countLabel(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export default function AppSidebar({
  courses,
  loading,
  loadError = null,
  onRetry,
  onNewCourse,
  query,
  onQueryChange,
}: {
  courses: Course[];
  loading: boolean;
  // Set only when the library could not be loaded at all: the list is then not
  // "empty", it is unknown, so this replaces the "No courses yet." line.
  loadError?: string | null;
  onRetry?: () => void;
  onNewCourse: () => void;
  query: string;
  onQueryChange: (query: string) => void;
}) {
  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="flex-row items-center justify-between px-4 py-4 gap-2 group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-2">
        <span className="flex items-center gap-2 min-w-0">
          <img src="/nucera-mark.svg" alt="" className="h-6 w-6 shrink-0" />
          <span className="font-brand text-base font-semibold tracking-tight text-sidebar-foreground truncate group-data-[collapsible=icon]:hidden">
            nucera
          </span>
        </span>
        <div className="flex items-center gap-1 group-data-[collapsible=icon]:hidden">
          <ThemeToggle />
          <SidebarTrigger className="text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent" />
        </div>
        {/* Icon rail is too narrow (3rem) for the logo mark and toggle
            side by side, so collapsed mode stacks the trigger below the
            mark instead (the row above becomes a column via flex-col). */}
        <SidebarTrigger className="hidden group-data-[collapsible=icon]:flex text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent" />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Library</SidebarGroupLabel>
          <SidebarGroupContent>
            <div className="relative mb-1 group-data-[collapsible=icon]:hidden">
              <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sidebar-foreground/50">
                <SearchIcon />
              </span>
              <Input
                value={query}
                onChange={(e) => onQueryChange(e.target.value)}
                placeholder="Search courses..."
                className="h-8 pl-8 bg-transparent border-sidebar-border text-sidebar-foreground placeholder:text-sidebar-foreground/50 focus-visible:ring-sidebar-ring"
              />
            </div>

            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton onClick={onNewCourse} tooltip="New course">
                  <PlusIcon />
                  <span>New course</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              {loading && (
                <p className="px-3 py-2 text-xs text-sidebar-foreground/70 group-data-[collapsible=icon]:hidden">
                  Loading...
                </p>
              )}
              {loadError && (
                <div
                  role="alert"
                  className="px-3 py-2 text-xs text-sidebar-foreground/80 group-data-[collapsible=icon]:hidden"
                >
                  <p>Couldn&apos;t load your courses.</p>
                  {onRetry && (
                    <button
                      type="button"
                      onClick={onRetry}
                      className="mt-1 underline underline-offset-2 hover:text-sidebar-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring rounded-sm"
                    >
                      Try again
                    </button>
                  )}
                </div>
              )}
              {!loading && !loadError && courses.length === 0 && (
                <p className="px-3 py-2 text-xs text-sidebar-foreground/70 group-data-[collapsible=icon]:hidden">
                  {query ? "No courses match your search." : "No courses yet."}
                </p>
              )}
              {courses.map((course) => {
                const badge = badgeColorFor(course.name);
                return (
                  <SidebarMenuItem key={course.id}>
                    <SidebarMenuButton asChild tooltip={course.name} className="group-data-[collapsible=icon]:p-1! h-auto py-1.5">
                      <Link href={courseHref(course.id)}>
                        <span
                          className="h-6 w-6 rounded-md border flex items-center justify-center text-[10px] font-semibold shrink-0"
                          style={{ background: badge.bg, borderColor: badge.border, color: badge.text }}
                        >
                          {course.name.charAt(0).toUpperCase()}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate">{course.name}</span>
                          <span className="block truncate text-[11px] text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden">
                            {countLabel(course.module_count, "module")} · {countLabel(course.topic_count, "topic")}
                          </span>
                        </span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="gap-2">
        <div className="hidden group-data-[collapsible=icon]:flex justify-center">
          <ThemeToggle />
        </div>
        <AccountMenu />
      </SidebarFooter>
    </Sidebar>
  );
}
