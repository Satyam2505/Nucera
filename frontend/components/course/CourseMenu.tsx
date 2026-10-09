"use client";

import { useState } from "react";

import ConfirmDeleteDialog from "@/components/course/ConfirmDeleteDialog";
import NameDialog from "@/components/course/NameDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, CourseTree } from "@/lib/api";

function DotsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <circle cx="5" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="19" cy="12" r="1.8" />
    </svg>
  );
}

interface Props {
  course: Pick<CourseTree, "id" | "name" | "description"> & { topicCount: number };
  // After a rename: refetch the tree and refresh app-wide state.
  onRenamed: () => Promise<void>;
  // After a delete: refresh app-wide state and leave the (now gone) course.
  onDeleted: () => Promise<void>;
}

export default function CourseMenu({ course, onRenamed, onDeleted }: Props) {
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          className="shrink-0 p-1.5 rounded-lg text-fg-secondary hover:text-[var(--ink)] hover:bg-[rgba(var(--ink-rgb),0.08)] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(var(--accent-rgb),0.4)]"
          aria-label="Course actions"
          title="Course actions"
        >
          <DotsIcon />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuItem onSelect={() => setDialog("rename")}>Rename course</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onSelect={() => setDialog("delete")}>
            Delete course
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {dialog === "rename" && (
        <NameDialog
          title="Rename course"
          nameLabel="Course name"
          submitLabel="Save"
          initialName={course.name}
          initialDescription={course.description}
          withDescription
          onSubmit={async (name, description) => {
            await api.updateCourse(course.id, { name, description: description || null });
            await onRenamed();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "delete" && (
        <ConfirmDeleteDialog
          title={`Delete course "${course.name}"?`}
          description={
            course.topicCount === 0
              ? "This removes the course and its modules."
              : `This removes the course, its modules and all ${course.topicCount} topic${
                  course.topicCount === 1 ? "" : "s"
                } with their sources and progress. This can't be undone.`
          }
          onConfirm={async () => {
            await api.deleteCourse(course.id);
            await onDeleted();
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}
