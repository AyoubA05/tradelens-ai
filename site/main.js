/* TradeLens AI — marketing site behavior (vanilla, no dependencies) */

const APP_URL = "https://app.tradelens.example"; // TODO: replace with deployed app URL

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const smallScreen = window.matchMedia("(max-width: 768px)").matches;
const saveData = navigator.connection && navigator.connection.saveData;

document.querySelectorAll("[data-app-link]").forEach((a) => {
  a.href = APP_URL;
});

/* ---- nav: mobile menu + scrolled state ---- */

const nav = document.querySelector(".nav");
const navToggle = document.querySelector(".nav-toggle");
const navLinks = document.getElementById("nav-links");

if (navToggle && navLinks) {
  navToggle.addEventListener("click", () => {
    const open = navLinks.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(open));
    navToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  });
  navLinks.addEventListener("click", (e) => {
    if (e.target.closest("a")) {
      navLinks.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
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

/* ---- videos: suppress on small screens, reduced motion, or Save-Data ---- */

if (smallScreen || reducedMotion || saveData) {
  document.querySelectorAll("video").forEach((v) => {
    v.removeAttribute("autoplay");
    v.querySelectorAll("source").forEach((s) => s.remove());
    v.load(); // poster remains
  });
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
