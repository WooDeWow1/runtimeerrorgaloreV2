import { Copy, Send } from "lucide-react";
import { toast } from "sonner";

const CAPTION =
  "Levelling up in Pokémon GO the easy way — PokeCoins does the raids, eggs and stardust grind for me. Use my link for legit, fast delivery:";

const copyCaption = async (text, label) => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${label} caption copied — paste it in your post`);
  } catch {
    toast.error("Copy blocked by your browser — copy the link above manually");
  }
};

// X has a share intent; Discord and TikTok have none, so those copy a ready-written caption.
export const ShareButtons = ({ link }) => {
  const message = `${CAPTION} ${link}`;
  const buttons = [
    {
      key: "x",
      label: "Share on X",
      action: () =>
        window.open(
          `https://twitter.com/intent/tweet?text=${encodeURIComponent(message)}`,
          "_blank",
          "noopener"
        ),
      icon: Send,
    },
    {
      key: "discord",
      label: "Copy for Discord",
      action: () => copyCaption(message, "Discord"),
      icon: Copy,
    },
    {
      key: "tiktok",
      label: "Copy for TikTok",
      action: () => copyCaption(`${CAPTION} ${link}`, "TikTok"),
      icon: Copy,
    },
  ];

  return (
    <div data-testid="share-buttons" className="mt-5">
      <p className="text-[10px] uppercase tracking-[0.25em] text-zinc-500">Share it in one tap</p>
      <div className="mt-3 flex flex-wrap gap-3">
        {buttons.map((b) => (
          <button
            key={b.key}
            data-testid={`share-${b.key}-btn`}
            onClick={b.action}
            className="flex items-center gap-2 border border-zinc-800 px-4 py-2.5 text-[10px] uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
          >
            <b.icon className="h-3 w-3" /> {b.label}
          </button>
        ))}
      </div>
    </div>
  );
};
