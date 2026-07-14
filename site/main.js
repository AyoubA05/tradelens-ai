/* TradeLens AI — marketing site behavior (vanilla, no dependencies) */

const APP_URL = "https://app.tradelens.example"; // TODO: replace with deployed app URL

document.querySelectorAll("[data-app-link]").forEach((a) => {
  a.href = APP_URL;
});
