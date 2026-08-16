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
   started fetching the MP4. The markup ships without a source, so an
   ineligible visitor never requests the file at all and keeps the poster.

   A blanket `max-width: 768px` gate used to sit here, which meant every
   phone got a still poster where the design calls for motion — the videos
   were "broken" on mobile by construction. Viewport width is the wrong
   proxy anyway: it says nothing about the connection paying for the file.
   Proximity does. Each video now hydrates when it is about to be seen and
   pauses when it leaves, so a phone downloads the hero and nothing else
   until the visitor scrolls to it.

   The two preferences that are real statements of intent are still
   honoured absolutely: reduced motion and Save-Data keep the poster. */

function hydrateVideo(video) {
  if (video.dataset.hydrated) return;
  video.dataset.hydrated = "true";
  const source = document.createElement("source");
  source.src = video.dataset.videoSrc;
  source.type = "video/mp4";
  video.appendChild(source);
  video.load();
  video.play().catch(() => {});
}

function watchEligibleVideos() {
  if (reducedMotion || saveData) return;
  const videos = document.querySelectorAll("video[data-video-src]");

  if (!("IntersectionObserver" in window)) {
    videos.forEach(hydrateVideo);
    return;
  }

  const nearby = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          hydrateVideo(entry.target);
          entry.target.play().catch(() => {});
        } else if (entry.target.dataset.hydrated) {
          // Decoding a video nobody is looking at costs battery on the
          // devices this change was made for.
          entry.target.pause();
        }
      });
    },
    { rootMargin: "200px 0px" }
  );

  videos.forEach((video) => nearby.observe(video));
}

watchEligibleVideos();

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
        // The rotator is already marked as one animation unit, and the
        // screen-reader copy of the sentence must not be split into spans.
        // Recursing into either would wrap their inner text and break them.
        if (child.classList.contains("w") || child.classList.contains("sr-only")) return;
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

/* ---- hero rotating word ----

   The headline names the thing a journal actually surfaces, and there is
   more than one of them. Cycling the noun says that faster than a list
   would, and every word has to stay true to what the product does: these
   are all things a completed trade already contains, never anything the
   product predicts.

   Width is animated, which means it has to be an explicit pixel value —
   `auto` does not transition. It is measured from the words themselves
   after webfonts land, because measuring against the fallback face bakes
   in the wrong number and the rule underneath ends up short. */

const rotator = document.querySelector(".rotator");

if (rotator) {
  const words = [...rotator.querySelectorAll(".rot-word")];
  let index = 0;

  const fitToCurrentWord = () => {
    rotator.style.width = `${words[index].getBoundingClientRect().width}px`;
  };

  const advance = () => {
    // A word rotating in a tab nobody is looking at is pure battery cost.
    if (document.hidden) return;
    const outgoing = words[index];
    index = (index + 1) % words.length;
    outgoing.classList.remove("is-current");
    outgoing.classList.add("is-leaving");
    words[index].classList.add("is-current");
    fitToCurrentWord();
    // Longer than the 560ms transition, so the reset never lands mid-move.
    setTimeout(() => outgoing.classList.remove("is-leaving"), 620);
  };

  const start = () => {
    fitToCurrentWord();
    if (reducedMotion || words.length < 2) return;
    setInterval(advance, 2400);
  };

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(start);
  } else {
    start();
  }

  window.addEventListener("resize", fitToCurrentWord, { passive: true });
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
