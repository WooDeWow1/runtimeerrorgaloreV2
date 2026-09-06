const KEY = "pokecoins_ref";
const WINDOW_DAYS = 30;

// A referral is captured from ?ref= and kept for the shop's 30 day attribution window, so a
// visitor who comes back later still credits the promoter who sent them.
export const captureRef = () => {
  const code = new URLSearchParams(window.location.search).get("ref");
  if (!code) return;
  const clean = code.trim().toUpperCase().slice(0, 16);
  if (!clean) return;
  localStorage.setItem(
    KEY,
    JSON.stringify({ code: clean, expires: Date.now() + WINDOW_DAYS * 86400000 })
  );
};

export const storedRef = () => {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "null");
    if (!raw || raw.expires < Date.now()) return null;
    return raw.code;
  } catch {
    return null;
  }
};
