"use client";

import { ReactNode, useState } from "react";

import ConfirmDeleteDialog from "@/components/course/ConfirmDeleteDialog";
import NameDialog from "@/components/course/NameDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api, CourseTree, Mastery, TreeModule, TreeTopic } from "@/lib/api";
import { STATUS_COLOR, type MasteryStatusKey } from "@/lib/status-colors";

function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="M19 21 12 16 5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      className={`shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
    >
      <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DotsIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <circle cx="5" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="19" cy="12" r="1.8" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}

type Dialog =
  | { kind: "addModule" }
  | { kind: "renameModule"; module: TreeModule }
  | { kind: "deleteModule"; module: TreeModule }
  | { kind: "addTopic"; module: TreeModule }
  | { kind: "renameTopic"; topic: TreeTopic }
  | { kind: "deleteTopic"; topic: TreeTopic };

interface Props {
  tree: CourseTree;
  activeTopicId: number | null;
  masteryByTopic: Record<number, Mastery>;
  onSelectTopic: (topicId: number) => void;
  onToggleRevision: (topicId: number) => Promise<void>;
  // Called after every structural change. When the API already returned the
  // new tree it is passed along; otherwise the caller refetches. Either way
  // the caller also refreshes app-wide state (sidebar counts, landing page).
  onChanged: (tree?: CourseTree) => Promise<void>;
}

const triggerClass =
  "shrink-0 p-1.5 rounded-lg text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent transition " +
  "opacity-70 md:opacity-0 md:group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring";

function RowMenu({ label, children }: { label: string; children: ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className={triggerClass} aria-label={label} title={label}>
        <DotsIcon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function moveId(ids: number[], index: number, delta: -1 | 1): number[] {
  const next = [...ids];
  const target = index + delta;
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export default function ModuleRail({
  tree,
  activeTopicId,
  masteryByTopic,
  onSelectTopic,
  onToggleRevision,
  onChanged,
}: Props) {
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [dialog, setDialog] = useState<Dialog | null>(null);
  // True while a reorder/move request is in flight, so rapid clicks on the
  // arrows can't send conflicting orders computed from a stale tree.
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function run(action: () => Promise<CourseTree | void>) {
    if (pending) return;
    setPending(true);
    setActionError(null);
    try {
      const updated = await action();
      await onChanged(updated ?? undefined);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "That change didn't go through");
    } finally {
      setPending(false);
    }
  }

  function toggleCollapsed(moduleId: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(moduleId)) next.delete(moduleId);
      else next.add(moduleId);
      return next;
    });
  }

  const moduleIds = tree.modules.map((m) => m.id);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between px-2 pb-1">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-sidebar-foreground/60">Modules</p>
        <button
          onClick={() => setDialog({ kind: "addModule" })}
          className="p-1.5 rounded-lg text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
          aria-label="Add module"
          title="Add module"
        >
          <PlusIcon />
        </button>
      </div>

      {actionError && (
        <p role="alert" className="px-2 py-1 text-xs text-[var(--error-text)]">
          {actionError}
        </p>
      )}

      {tree.modules.length === 0 && (
        <div className="px-2 py-3 space-y-2">
          <p className="text-xs text-sidebar-foreground/70">This course has no modules yet.</p>
          <button
            onClick={() => setDialog({ kind: "addModule" })}
            className="text-xs font-medium text-[var(--accent)] hover:underline"
          >
            Add your first module
          </button>
        </div>
      )}

      {tree.modules.map((module, moduleIndex) => {
        const open = !collapsed.has(module.id);
        const topicIds = module.topics.map((t) => t.id);
        return (
          <section key={module.id} aria-label={module.name}>
            <div className="flex items-center gap-1 group mt-2">
              <button
                onClick={() => toggleCollapsed(module.id)}
                aria-expanded={open}
                className="flex-1 min-w-0 flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-xs font-semibold text-sidebar-foreground/80 hover:text-sidebar-foreground hover:bg-sidebar-accent transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
              >
                <ChevronIcon open={open} />
                <span className="shrink-0 tabular-nums">{moduleIndex + 1}.</span>
                <span className="truncate">{module.name}</span>
              </button>
              <RowMenu label={`Actions for module ${module.name}`}>
                <DropdownMenuItem onSelect={() => setDialog({ kind: "addTopic", module })}>
                  Add topic
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setDialog({ kind: "renameModule", module })}>
                  Rename module
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={pending || moduleIndex === 0}
                  onSelect={() => run(() => api.reorderModules(tree.id, moveId(moduleIds, moduleIndex, -1)))}
                >
                  Move up
                </DropdownMenuItem>
                <DropdownMenuItem
                  disabled={pending || moduleIndex === moduleIds.length - 1}
                  onSelect={() => run(() => api.reorderModules(tree.id, moveId(moduleIds, moduleIndex, 1)))}
                >
                  Move down
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => setDialog({ kind: "deleteModule", module })}>
                  Delete module
                </DropdownMenuItem>
              </RowMenu>
            </div>

            {open && (
              <div className="space-y-0.5 mt-0.5">
                {module.topics.length === 0 && (
                  <div className="pl-7 pr-2 py-1.5 flex items-center gap-2">
                    <p className="text-xs text-sidebar-foreground/60">No topics yet.</p>
                    <button
                      onClick={() => setDialog({ kind: "addTopic", module })}
                      className="text-xs font-medium text-[var(--accent)] hover:underline"
                    >
                      Add topic
                    </button>
                  </div>
                )}
                {module.topics.map((topic, topicIndex) => {
                  const mastery = masteryByTopic[topic.id];
                  const status = (mastery?.status ?? topic.status) as MasteryStatusKey;
                  const flagged = mastery?.flagged_for_revision ?? topic.flagged_for_revision;
                  const active = topic.id === activeTopicId;
                  const otherModules = tree.modules.filter((m) => m.id !== module.id);
                  return (
                    <div key={topic.id} className="flex items-center gap-1 group">
                      <button
                        onClick={() => onSelectTopic(topic.id)}
                        aria-current={active ? "true" : undefined}
                        className={`flex-1 min-w-0 flex items-center gap-2.5 rounded-lg pl-7 pr-3 py-2 text-left text-sm transition border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring ${
                          active
                            ? "bg-[rgba(var(--accent-rgb),0.18)] text-white border-[rgba(var(--accent-rgb),0.4)]"
                            : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground border-transparent"
                        }`}
                      >
                        <span
                          className="h-1.5 w-1.5 rounded-full shrink-0"
                          style={{ background: STATUS_COLOR[status] }}
                          aria-hidden
                        />
                        <span className="truncate">{topic.name}</span>
                      </button>
                      <button
                        onClick={() => onToggleRevision(topic.id)}
                        className={`shrink-0 p-1.5 rounded-lg transition focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring ${
                          flagged
                            ? "text-[var(--accent)] opacity-100"
                            : "text-sidebar-foreground/40 opacity-0 group-hover:opacity-100 hover:text-sidebar-foreground/80"
                        }`}
                        aria-label={flagged ? "Remove from revision list" : "Add to revision list"}
                        title={flagged ? "Remove from revision list" : "Add to revision list"}
                      >
                        <BookmarkIcon filled={flagged} />
                      </button>
                      <RowMenu label={`Actions for topic ${topic.name}`}>
                        <DropdownMenuItem onSelect={() => setDialog({ kind: "renameTopic", topic })}>
                          Rename topic
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          disabled={pending || topicIndex === 0}
                          onSelect={() => run(() => api.reorderTopics(module.id, moveId(topicIds, topicIndex, -1)))}
                        >
                          Move up
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          disabled={pending || topicIndex === topicIds.length - 1}
                          onSelect={() => run(() => api.reorderTopics(module.id, moveId(topicIds, topicIndex, 1)))}
                        >
                          Move down
                        </DropdownMenuItem>
                        {otherModules.length > 0 && (
                          <DropdownMenuSub>
                            <DropdownMenuSubTrigger disabled={pending}>Move to module</DropdownMenuSubTrigger>
                            <DropdownMenuSubContent>
                              {otherModules.map((target) => (
                                <DropdownMenuItem
                                  key={target.id}
                                  disabled={pending}
                                  onSelect={() =>
                                    run(async () => {
                                      await api.updateTopic(topic.id, { module_id: target.id });
                                    })
                                  }
                                >
                                  {target.name}
                                </DropdownMenuItem>
                              ))}
                            </DropdownMenuSubContent>
                          </DropdownMenuSub>
                        )}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          variant="destructive"
                          onSelect={() => setDialog({ kind: "deleteTopic", topic })}
                        >
                          Delete topic
                        </DropdownMenuItem>
                      </RowMenu>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        );
      })}

      {dialog?.kind === "addModule" && (
        <NameDialog
          title="Add a module"
          nameLabel="Module name"
          namePlaceholder="e.g. Processes and Threads"
          submitLabel="Add module"
          onSubmit={async (name) => {
            await api.createModule(tree.id, { name });
            await onChanged();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "renameModule" && (
        <NameDialog
          title="Rename module"
          nameLabel="Module name"
          submitLabel="Save"
          initialName={dialog.module.name}
          onSubmit={async (name) => {
            await onChanged(await api.updateModule(dialog.module.id, { name }));
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "addTopic" && (
        <NameDialog
          title={`Add a topic to ${dialog.module.name}`}
          nameLabel="Topic name"
          namePlaceholder="e.g. Scheduling"
          submitLabel="Add topic"
          onSubmit={async (name) => {
            await api.createTopic({ name, module_id: dialog.module.id });
            await onChanged();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "renameTopic" && (
        <NameDialog
          title="Rename topic"
          nameLabel="Topic name"
          submitLabel="Save"
          initialName={dialog.topic.name}
          onSubmit={async (name) => {
            await api.updateTopic(dialog.topic.id, { name });
            await onChanged();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "deleteModule" && (
        <ConfirmDeleteDialog
          title={`Delete module "${dialog.module.name}"?`}
          description={
            dialog.module.topics.length === 0
              ? "This module has no topics."
              : `This also deletes its ${dialog.module.topics.length} topic${
                  dialog.module.topics.length === 1 ? "" : "s"
                } along with their sources and progress. This can't be undone.`
          }
          onConfirm={async () => {
            await api.deleteModule(dialog.module.id);
            await onChanged();
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "deleteTopic" && (
        <ConfirmDeleteDialog
          title={`Delete topic "${dialog.topic.name}"?`}
          description="This also deletes its sources and progress. This can't be undone."
          onConfirm={async () => {
            await api.deleteTopic(dialog.topic.id);
            await onChanged();
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
