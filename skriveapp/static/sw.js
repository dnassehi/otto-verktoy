// Minimal service worker - kun til stede for at Chrome/Edge skal anse
// appen som "installerbar". Ingen offline-caching (bevisst - dokumentene
// skal alltid hentes ferske fra serveren).
self.addEventListener("fetch", () => {});
