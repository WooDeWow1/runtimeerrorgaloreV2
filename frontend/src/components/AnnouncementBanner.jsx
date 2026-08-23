import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "@/lib/api";

export const AnnouncementBanner = () => {
  const [banner, setBanner] = useState(null);
  const [closed, setClosed] = useState(false);

  useEffect(() => {
    api.get("/settings/banner").then(({ data }) => setBanner(data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (banner?.text) setClosed(sessionStorage.getItem("pokecoins_banner") === banner.text);
  }, [banner]);

  if (!banner?.enabled || !banner.text || closed) return null;

  const dismiss = () => {
    sessionStorage.setItem("pokecoins_banner", banner.text);
    setClosed(true);
  };

  return (
    <div
      data-testid="announcement-banner"
      className="relative flex items-center justify-center gap-3 border-b border-[#00ffcc]/30 bg-[#00ffcc]/10 px-10 py-2.5 text-center"
    >
      <p className="text-[11px] uppercase tracking-[0.2em] text-[#00ffcc]">
        {banner.text}
        {banner.link_url && (
          <a
            href={banner.link_url}
            data-testid="banner-link"
            className="ml-3 border-b border-[#00ffcc] pb-0.5 font-bold hover:text-white hover:border-white"
          >
            {banner.link_label || "Shop now"}
          </a>
        )}
      </p>
      <button
        data-testid="banner-dismiss"
        onClick={dismiss}
        aria-label="Dismiss announcement"
        className="absolute right-4 text-[#00ffcc]/60 transition-colors hover:text-[#00ffcc]"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};
