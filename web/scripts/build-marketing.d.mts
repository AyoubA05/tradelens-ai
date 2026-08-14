/**
 * Types for the marketing prebuild step.
 *
 * The script itself stays plain `.mjs` because Vercel runs it with bare Node
 * before any TypeScript toolchain exists in the build. Its test imports it, so
 * without this declaration `tsc --noEmit` fails with TS7016 while the test
 * suite and `next build` both pass — Next only typechecks the files in its own
 * build graph, and `__tests__` is not one of them.
 */

export interface MarketingBuildOptions {
  siteOrigin?: string;
  appOrigin?: string;
  supportEmail?: string;
  /** Overridable for tests; production uses ../../site and ../public. */
  sourceDir?: string;
  outputDir?: string;
}

export interface MarketingBuildResult {
  site: string;
  app: string;
  support: string;
}

export function validateOrigin(
  value: string | undefined,
  name: string,
  options?: { allowLocal?: boolean },
): string;

export function validateSupportEmail(value: string | undefined): string;

export function buildMarketing(
  options?: MarketingBuildOptions,
): Promise<MarketingBuildResult>;
