import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "@/lib/api";
import { Markdown } from "@/components/Markdown";

const TABS = [
  { key: "privacy", label: "Privacy Policy" },
  { key: "terms", label: "Terms of Service" },
];

export default function Legal() {
  const [params, setParams] = useSearchParams();
  const doc = params.get("doc") === "terms" ? "terms" : "privacy";
  const [data, setData] = useState(null);

  const load = useCallback(
    () => api.get("/legal").then(({ data: d }) => setData(d)).catch(() => {}),
    []
  );

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div data-testid="legal-page" className="px-5 py-16 lg:px-10 lg:py-24">
      <div className="mx-auto max-w-[720px]">
        <p className="text-[10px] uppercase tracking-[0.3em] text-[#00ffcc]">// legal center</p>
        <h1 className="mt-4 font-display text-4xl tracking-tighter sm:text-5xl">Legal</h1>
        <p className="mt-4 text-sm leading-relaxed text-zinc-500">
          Everything about how we handle your order, your account access and your data. Questions:{" "}
          <a href="mailto:support@pokecoins.cc" className="text-[#00ffcc]">
            support@pokecoins.cc
          </a>
        </p>

        <div className="mt-10 flex gap-2 border-b border-[#1f1f1f]">
          {TABS.map((t) => (
            <button
              key={t.key}
              data-testid={`legal-tab-${t.key}`}
              onClick={() => setParams({ doc: t.key })}
              className={`px-5 py-3 text-[10px] uppercase tracking-[0.25em] transition-colors ${
                doc === t.key
                  ? "border-b-2 border-[#00ffcc] text-[#00ffcc]"
                  : "text-zinc-500 hover:text-white"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {data ? (
          <article data-testid={`legal-body-${doc}`} className="mt-10">
            <Markdown text={data[doc]} />
          </article>
        ) : (
          <p className="mt-10 text-xs text-zinc-600">Loading…</p>
        )}
      </div>
    </div>
  );
}
