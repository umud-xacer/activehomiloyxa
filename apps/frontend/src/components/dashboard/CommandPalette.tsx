import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";

export interface CommandAction {
  label: string;
  to: string;
  icon: LucideIcon;
  group?: string;
  shortcut?: string;
}

/** Arc/Linear-style ⌘K palette -- global keyboard shortcut wires up once, mounted by
 * `DashboardShell` so every workspace page gets it for free. */
export function CommandPalette({ actions }: { actions: CommandAction[] }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const groups = actions.reduce<Record<string, CommandAction[]>>((acc, a) => {
    const key = a.group ?? "Tezkor harakatlar";
    (acc[key] ??= []).push(a);
    return acc;
  }, {});

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Buyruq yoki sahifa qidiring..." />
      <CommandList>
        <CommandEmpty>Hech narsa topilmadi.</CommandEmpty>
        {Object.entries(groups).map(([group, items]) => (
          <CommandGroup key={group} heading={group}>
            {items.map((a) => (
              <CommandItem
                key={a.to + a.label}
                onSelect={() => {
                  setOpen(false);
                  navigate({ to: a.to });
                }}
              >
                <a.icon />
                <span>{a.label}</span>
                {a.shortcut && <CommandShortcut>{a.shortcut}</CommandShortcut>}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}

export function useCommandPaletteHint(): string {
  const isMac = typeof navigator !== "undefined" && /Mac/.test(navigator.platform);
  return isMac ? "⌘K" : "Ctrl K";
}
