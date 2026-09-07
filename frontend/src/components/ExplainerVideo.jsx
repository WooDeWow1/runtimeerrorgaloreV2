import { useRef, useState } from "react";
import { Play } from "lucide-react";

// Manual player: no autoplay, native controls give play/pause, seeking, volume and mute.
// The poster + neon overlay keeps it on-theme until the customer chooses to watch.
export const ExplainerVideo = ({ src, poster }) => {
  const ref = useRef(null);
  const [started, setStarted] = useState(false);
  const [failed, setFailed] = useState(false);

  // play() rejects when the browser cannot decode the file or blocks playback: swallow it and
  // say so, rather than leaking an unhandled promise rejection.
  const start = async () => {
    try {
      await ref.current?.play();
      setStarted(true);
    } catch {
      setFailed(true);
    }
  };

  return (
    <div
      data-testid="explainer-video-frame"
      className="group relative overflow-hidden border border-[#00ffcc]/30 bg-black shadow-[0_0_40px_-12px_rgba(0,255,204,0.35)]"
    >
      <video
        ref={ref}
        data-testid="explainer-video"
        src={src}
        poster={poster}
        controls
        controlsList="nodownload"
        playsInline
        preload="metadata"
        onError={() => setFailed(true)}
        className="block aspect-video w-full bg-black"
      />
      {failed && (
        <p
          data-testid="explainer-video-error"
          className="border-t border-[#ff3b30]/30 bg-[#ff3b30]/5 px-4 py-3 text-center text-[10px] uppercase tracking-[0.2em] text-[#ff3b30]"
        >
          This video cannot play in your browser
        </p>
      )}
      {!started && !failed && (
        <button
          data-testid="explainer-play-btn"
          onClick={start}
          aria-label="Play the explainer video"
          className="absolute inset-x-0 top-0 flex aspect-video items-center justify-center bg-[#050505]/45 transition-colors hover:bg-[#050505]/25"
        >
          <span className="flex h-16 w-16 items-center justify-center rounded-full border border-[#00ffcc] bg-[#050505]/80 text-[#00ffcc] transition-transform group-hover:scale-110">
            <Play className="h-6 w-6 translate-x-0.5" />
          </span>
        </button>
      )}
    </div>
  );
};
