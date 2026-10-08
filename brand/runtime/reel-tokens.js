/* Kit to Clip brand runtime (copied into the project by bridge.py): reads the brand pack's token contract, the --reel-*
   CSS variables in brand.css, for neutral formats. Load it after gsap (and CustomEase, for the brand's own curves).
     REEL.ease("enter" | "exit" | "move" | "expressive")  a GSAP ease from --reel-ease-* (CustomEase when loaded)
     REEL.dur("enter" | "exit" | "move" | "expressive")   seconds from --reel-dur-*
     REEL.stagger()                         seconds between items in a list (--reel-stagger, else by energy)
     REEL.token(name)                       any --reel-<name> value, trimmed
     REEL.energy                            "calm" | "steady" | "punchy"
     REEL.brand                             window.REEL_BRAND from the pack's brand-snippets.js
     REEL.sting                             REEL_BRAND.sting: { seconds, silentTail, rules: [...] } or null
     REEL.rules                             REEL_BRAND.motionRules: the brand's written motion rules, or []
   "expressive" is the brand's signature register (stings, title cards, the climax); enter/exit/move are the everyday,
   productive register. Optional tokens fall back to sensible values, so older packs work unchanged. */
(function () {
  const FALLBACK = { enter: "power3.out", exit: "power2.in", move: "power2.inOut", expressive: "expo.out" };
  const STAGGER_BY_ENERGY = { calm: 0.08, steady: 0.05, punchy: 0.03 };
  const made = {};
  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(`--reel-${name}`).trim();
  window.REEL = {
    token,
    get brand() { return window.REEL_BRAND || null; },
    get energy() { return token("energy") || "steady"; },
    get sting() { return (window.REEL_BRAND && window.REEL_BRAND.sting) || null; },
    get rules() { return (window.REEL_BRAND && window.REEL_BRAND.motionRules) || []; },
    dur(name) {
      const s = parseFloat(token(`dur-${name}`));
      if (Number.isFinite(s) && s > 0) return s;
      if (name === "expressive") return Math.round(window.REEL.dur("enter") * 1.4 * 1000) / 1000;
      return 0.5;
    },
    stagger() {
      const s = parseFloat(token("stagger"));
      return Number.isFinite(s) && s >= 0 ? s : STAGGER_BY_ENERGY[window.REEL.energy] || 0.05;
    },
    ease(name) {
      if (made[name]) return made[name];
      const m = /cubic-bezier\(([^)]+)\)/.exec(token(`ease-${name}`));
      if (m && window.gsap && window.CustomEase) {
        window.gsap.registerPlugin(window.CustomEase);
        window.CustomEase.create(`reel-${name}`, m[1].replace(/\s+/g, ""));
        return (made[name] = `reel-${name}`);
      }
      if (name === "expressive" && !token("ease-expressive")) return (made[name] = window.REEL.ease("enter") === "power3.out" ? FALLBACK.expressive : window.REEL.ease("enter"));
      return (made[name] = FALLBACK[name] || "power2.out");
    },
  };
})();
