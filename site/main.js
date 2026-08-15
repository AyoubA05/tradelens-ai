/* TradeLens AI — marketing site behavior (vanilla, no dependencies) */

/* The journal CTAs point at /login, in the markup, and nothing rewrites them.
 *
 * They used to carry `data-app-link` and this file replaced every such href
 * with APP_ORIGIN at runtime, sending visitors straight to the Streamlit host.
 * That was correct while Streamlit owned sign-in. It is wrong now: arriving
 * there without a handoff credential drops the visitor on the legacy login
 * screen, bypassing the website auth flow entirely.
 *
 * `/login` is relative because the marketing site and the auth routes are the
 * same origin — Vercel's Root Directory is web/, which serves this site from
 * public/ alongside the Next routes. A relative link therefore needs no build
 * token, cannot drift from SITE_ORIGIN, and works identically on a preview
 * deployment.
 *
 * APP_ORIGIN is unchanged and still required: /continue reads it server-side
 * as the handoff destination. The marketing site simply no longer links to it.
 */

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const smallScreen = window.matchMedia("(max-width: 768px)").matches;
const saveData = navigator.connection && navigator.connection.saveData;

/* ---- nav: mobile menu + scrolled state ---- */

const nav = document.querySelector(".nav");
const navToggle = document.querySelector(".nav-toggle");
const navLinks = document.getElementById("nav-links");

if (navToggle && navLinks) {
  navToggle.addEventListener("click", () => {
    const open = navLinks.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(open));
    navToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    document.body.classList.toggle("menu-open", open);
  });
  navLinks.addEventListener("click", (e) => {
    if (e.target.closest("a")) {
      navLinks.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
      document.body.classList.remove("menu-open");
    }
  });
}

let scrollTicking = false;
window.addEventListener(
  "scroll",
  () => {
    if (scrollTicking) return;
    scrollTicking = true;
    requestAnimationFrame(() => {
      nav.classList.toggle("scrolled", window.scrollY > 40);
      scrollTicking = false;
    });
  },
  { passive: true }
);

/* ---- videos: attached only when the visitor's device and preferences allow

   Removing <source> after parse was too late — the browser had already
   started fetching the MP4. The markup now ships without a source, so an
   ineligible visitor never requests the file at all and keeps the poster. */

function hydrateEligibleVideos() {
  if (smallScreen || reducedMotion || saveData) return;
  document.querySelectorAll("video[data-video-src]").forEach((video) => {
    const source = document.createElement("source");
    source.src = video.dataset.videoSrc;
    source.type = "video/mp4";
    video.appendChild(source);
    video.load();
    video.play().catch(() => {});
  });
}

hydrateEligibleVideos();

/* ---- tilt showcase: card straightens as it scrolls into view ---- */

const tiltCard = document.querySelector(".tilt-card");

if (tiltCard && !reducedMotion) {
  let tiltTicking = false;
  const updateTilt = () => {
    const rect = tiltCard.getBoundingClientRect();
    const vh = window.innerHeight;
    // progress 0 → 1 as the card travels from below the fold to 10% up the viewport
    const raw = (vh - rect.top) / (vh * 0.9);
    const p = Math.min(1, Math.max(0, raw));
    const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
    tiltCard.style.setProperty("--tilt", `${16 * (1 - eased)}deg`);
    tiltCard.style.setProperty("--tilt-scale", String(0.96 + 0.04 * eased));
  };
  updateTilt();
  window.addEventListener(
    "scroll",
    () => {
      if (tiltTicking) return;
      tiltTicking = true;
      requestAnimationFrame(() => {
        updateTilt();
        tiltTicking = false;
      });
    },
    { passive: true }
  );
}

/* ---- how-it-works: candles + lines draw with scroll (set-piece) ---- */

const howSection = document.getElementById("how");

if (howSection && !reducedMotion) {
  howSection.style.setProperty("--how-p", "0");
  let howTicking = false;
  const updateHow = () => {
    const r = howSection.getBoundingClientRect();
    const vh = window.innerHeight;
    const p = Math.min(1, Math.max(0, (vh * 0.9 - r.top) / (r.height + vh * 0.3)));
    howSection.style.setProperty("--how-p", p.toFixed(4));
  };
  updateHow();
  window.addEventListener(
    "scroll",
    () => {
      if (howTicking) return;
      howTicking = true;
      requestAnimationFrame(() => {
        updateHow();
        howTicking = false;
      });
    },
    { passive: true }
  );
}

/* ---- mobile sticky CTA: visible between hero and footer CTA band ---- */

const mobileCta = document.querySelector(".mobile-cta");

if (mobileCta && "IntersectionObserver" in window) {
  const heroEl = document.getElementById("hero");
  const ctaBand = document.getElementById("cta");
  const state = { heroVisible: true, bandVisible: false };
  const apply = () =>
    mobileCta.classList.toggle("show", !state.heroVisible && !state.bandVisible);
  const vis = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.target === heroEl) state.heroVisible = e.isIntersecting;
        if (e.target === ctaBand) state.bandVisible = e.isIntersecting;
      });
      apply();
    },
    { threshold: 0.05 }
  );
  vis.observe(heroEl);
  vis.observe(ctaBand);
}

/* ---- hero entrance: word-split stagger ---- */

const hero = document.querySelector(".hero");
const heroTitle = document.querySelector(".hero-title");

if (hero && heroTitle && !reducedMotion) {
  // wrap each word in a span, preserving the accent span around "Find Them."
  const wrapWords = (node) => {
    [...node.childNodes].forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) {
        const frag = document.createDocumentFragment();
        child.textContent.split(/(\s+)/).forEach((part) => {
          if (/^\s+$/.test(part) || part === "") {
            frag.appendChild(document.createTextNode(part));
          } else {
            const w = document.createElement("span");
            w.className = "w";
            w.textContent = part;
            frag.appendChild(w);
          }
        });
        child.replaceWith(frag);
      } else if (child.nodeType === Node.ELEMENT_NODE) {
        wrapWords(child);
      }
    });
  };
  wrapWords(heroTitle);
  heroTitle.querySelectorAll(".w").forEach((w, i) => {
    w.style.setProperty("--d", `${140 + i * 75}ms`);
  });
  hero.classList.add("will-animate");
  requestAnimationFrame(() => {
    requestAnimationFrame(() => hero.classList.add("loaded"));
  });
}

/* ---- conversion measurement: aggregate only, never personal ----

   Vercel Web Analytics is already loaded. These events record which CTA a
   visitor used and which questions get opened: enough to diagnose the
   funnel, and nothing that identifies a person. Only the two properties
   below are ever sent, both of them fixed strings from this page. */

function track(name, properties) {
  if (typeof window.va === "function") {
    window.va("event", { name, ...properties });
  }
}

document.querySelectorAll("[data-cta-location]").forEach((link) => {
  link.addEventListener("click", () => {
    track("marketing_cta_click", { location: link.dataset.ctaLocation });
  });
});

document.querySelectorAll(".faq-item").forEach((item) => {
  item.addEventListener("toggle", () => {
    if (item.open) {
      track("faq_open", { question: item.querySelector("summary").textContent });
    }
  });
});
