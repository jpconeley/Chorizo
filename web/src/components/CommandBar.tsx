"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { STAGE_LABEL, type SearchHit } from "@/lib/types";

/** Terminal-style command line: type to search, arrows to pick, Enter to open, "/" to focus. */
export function CommandBar() {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/search?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        setHits(res.ok ? await res.json() : []);
        setActive(0);
      } catch {
        // superseded by a newer keystroke
      }
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  // Short queries show nothing; stale results from a longer query stay hidden.
  const shown = query.trim().length >= 2 ? hits : [];

  const go = (hit?: SearchHit) => {
    setOpen(false);
    input.current?.blur();
    if (hit) router.push(`/assets/${hit.id}`);
    else if (query.trim()) router.push(`/screener?q=${encodeURIComponent(query.trim())}`);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, shown.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(shown[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      input.current?.blur();
    }
  };

  return (
    <div className="cmd">
      <span className="cmd-prompt">&gt;</span>
      <input
        ref={input}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
        placeholder="Search drug, target, sponsor"
        aria-label="Search"
        role="combobox"
        aria-expanded={open && shown.length > 0}
        aria-controls="cmd-results"
        spellCheck={false}
      />
      <kbd>/</kbd>
      {open && shown.length > 0 && (
        <ul id="cmd-results" className="cmd-results" role="listbox">
          {shown.map((hit, i) => (
            <li
              key={hit.id}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                go(hit);
              }}
            >
              <span className={`stage stage-${hit.stage}`}>{STAGE_LABEL[hit.stage]}</span>
              <span className="cmd-name">{hit.name}</span>
              <span className="muted">{hit.indication}</span>
              {hit.sponsor && <span className="muted cmd-sponsor">{hit.sponsor}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
