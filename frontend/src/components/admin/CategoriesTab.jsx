import { useState } from "react";
import { ArrowDown, ArrowUp, Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api, apiError } from "@/lib/api";

const input =
  "w-full bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";

export const CategoriesTab = ({ categories, reload }) => {
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState({ label: "", note: "", coming_soon: false });
  const [newLabel, setNewLabel] = useState("");

  const run = async (fn) => {
    try {
      await fn();
      await reload();
    } catch (err) {
      toast.error(apiError(err));
    }
  };

  const add = () => {
    if (!newLabel.trim()) return;
    run(async () => {
      await api.post("/admin/categories", { label: newLabel.trim() });
      toast.success("Category added");
      setNewLabel("");
    });
  };

  const save = (c) =>
    run(async () => {
      await api.put(`/admin/categories/${c.id}`, draft);
      toast.success("Category updated");
      setEditing(null);
    });

  const remove = (c) => {
    if (!window.confirm(`Delete category "${c.label}"? This cannot be undone.`)) return;
    run(async () => {
      await api.delete(`/admin/categories/${c.id}`);
      toast.success(`${c.label} deleted`);
    });
  };

  const move = (c, direction) =>
    run(() => api.post(`/admin/categories/${c.id}/move`, { direction }));

  return (
    <div className="mt-10" data-testid="categories-panel">
      <h2 className="font-display text-sm uppercase tracking-[0.2em]">Categories</h2>
      <p className="mt-2 max-w-2xl text-[10px] leading-relaxed text-zinc-600">
        These drive the storefront tabs and the order products appear in. A category can only be
        deleted once no products use it.
      </p>

      <div className="mt-6 flex flex-wrap gap-3">
        <input
          data-testid="new-category-input"
          className={`${input} max-w-xs`}
          placeholder="New category name"
          value={newLabel}
          onChange={(e) => setNewLabel(e.target.value)}
        />
        <button
          data-testid="add-category-btn"
          onClick={add}
          className="flex items-center gap-2 border border-[#00ffcc] px-4 py-2 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black"
        >
          <Plus className="h-3 w-3" /> Add
        </button>
      </div>

      <div className="mt-8 space-y-3">
        {categories.map((c, n) => (
          <div
            key={c.id}
            data-testid={`category-row-${c.key}`}
            className="flex flex-wrap items-center gap-3 border border-[#1f1f1f] bg-[#0a0a0a] p-4"
          >
            <span className="w-8 font-mono text-[10px] text-zinc-600">{n + 1}</span>
            {editing === c.id ? (
              <>
                <input
                  data-testid={`category-label-input-${c.key}`}
                  className={`${input} max-w-[240px]`}
                  value={draft.label}
                  onChange={(e) => setDraft({ ...draft, label: e.target.value })}
                />
                <input
                  className={`${input} max-w-[220px]`}
                  placeholder="Note (optional)"
                  value={draft.note}
                  onChange={(e) => setDraft({ ...draft, note: e.target.value })}
                />
                <label className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
                  <input
                    type="checkbox"
                    checked={draft.coming_soon}
                    onChange={(e) => setDraft({ ...draft, coming_soon: e.target.checked })}
                  />
                  Coming soon
                </label>
                <button
                  data-testid={`save-category-${c.key}`}
                  onClick={() => save(c)}
                  className="border border-[#00ffcc] p-2 text-[#00ffcc]"
                >
                  <Check className="h-3 w-3" />
                </button>
                <button onClick={() => setEditing(null)} className="border border-zinc-800 p-2 text-zinc-500">
                  <X className="h-3 w-3" />
                </button>
              </>
            ) : (
              <>
                <div className="min-w-[220px] flex-1">
                  <p className="text-xs font-bold">{c.label}</p>
                  <p className="mt-1 font-mono text-[10px] text-zinc-600">
                    {c.key}
                    {c.note ? ` · ${c.note}` : ""}
                    {c.coming_soon ? " · coming soon" : ""}
                  </p>
                </div>
                <button
                  data-testid={`move-up-${c.key}`}
                  onClick={() => move(c, "up")}
                  className="border border-zinc-800 p-2 text-zinc-400 hover:border-[#00ffcc] hover:text-[#00ffcc]"
                >
                  <ArrowUp className="h-3 w-3" />
                </button>
                <button
                  data-testid={`move-down-${c.key}`}
                  onClick={() => move(c, "down")}
                  className="border border-zinc-800 p-2 text-zinc-400 hover:border-[#00ffcc] hover:text-[#00ffcc]"
                >
                  <ArrowDown className="h-3 w-3" />
                </button>
                <button
                  data-testid={`edit-category-${c.key}`}
                  onClick={() => {
                    setEditing(c.id);
                    setDraft({ label: c.label, note: c.note || "", coming_soon: !!c.coming_soon });
                  }}
                  className="border border-zinc-800 p-2 text-zinc-400 hover:border-[#00ffcc] hover:text-[#00ffcc]"
                >
                  <Pencil className="h-3 w-3" />
                </button>
                <button
                  data-testid={`delete-category-${c.key}`}
                  onClick={() => remove(c)}
                  className="border border-zinc-800 p-2 text-zinc-400 hover:border-[#ff3b30] hover:text-[#ff3b30]"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
