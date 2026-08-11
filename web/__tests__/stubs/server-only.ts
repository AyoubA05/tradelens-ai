// Vitest cannot resolve Next.js's "server-only" marker package.
// It is a build-time guard, not runtime behaviour, so tests alias it to nothing.
export {};
