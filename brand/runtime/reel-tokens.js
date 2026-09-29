/* Kit to Clip brand runtime (copied into the project by bridge.py): reads the brand pack's token contract, the --reel-*
   CSS variables in brand.css, for neutral formats. Load it after gsap (and CustomEase, for the brand's own curves).
     REEL.ease("enter" | "exit" | "move")  a GSAP ease from --reel-ease-* (CustomEase when loaded)
     REEL.dur("enter" | "exit" | "move")   seconds from --reel-dur-*
     REEL.token(name)                       any --reel-<name> value, trimmed
     REEL.energy                            "calm" | "steady" | "punchy"
     REEL.brand                             window.REEL_BRAND from the pack's brand-snippets.js */
(function () {
  const FALLBACK = { enter: "power3.out", exit: "power2.in", move: "power2.inOut" };
  const made = {};
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(`--reel-${name}`).trim();
  window.REEL = {
    token,
    get brand() { return window.REEL_BRAND || null; },
    get energy() { return token("energy") || "steady"; },
    dur(name) {
      const s = parseFloat(token(`dur-${name}`));
      return Number.isFinite(s) && s > 0 ? s : 0.5;
    },
    ease(name) {
      if (made[name]) return made[name];
      const m = /cubic-bezier\(([^)]+)\)/.exec(token(`ease-${name}`));
      if (m && window.gsap && window.CustomEase) {
        window.gsap.registerPlugin(window.CustomEase);
        window.CustomEase.create(`reel-${name}`, m[1].replace(/\s+/g, ""));
        return (made[name] = `reel-${name}`);
      }
      return (made[name] = FALLBACK[name] || "power2.out");
    },
  };
})();
