/**
 * Credential domains for `auth_sessions`.
 *
 * Website and Streamlit sessions live in the same table. Before this existed
 * both hashed with a plain `sha256(token)`, so either token validated on either
 * surface — demonstrated on dev on 2026-08-13, where a Python-issued Streamlit
 * session was accepted by the website validator.
 *
 * That mattered because the two credentials have deliberately different
 * exposure: the website one is an HttpOnly cookie, the Streamlit one rides in a
 * URL and is a documented leaky bearer. Interchangeability turned that
 * asymmetry into a privilege bridge from the weakest credential to the
 * strongest.
 *
 * Two redundant controls now prevent it, and they fail differently:
 *
 *   this prefix       cross-surface acceptance is impossible by construction.
 *                     There is no WHERE clause to forget, because the hash
 *                     function each surface uses IS the domain.
 *   `surface` column  makes the domain explicit, auditable and queryable, and
 *                     is checked as defence in depth.
 *
 * Versioned so a future rotation stays unambiguous. UTF-8 throughout.
 *
 * There is deliberately **no fallback** to the old undomained hash. Trying both
 * would restore the exact ambiguity this replaces; `auth_sessions` was empty
 * when the change landed, so a clean cut costs nothing.
 */

export const WEBSITE_DOMAIN = "tl.website.v1|";
export const STREAMLIT_DOMAIN = "tl.streamlit.v1|";

export const SURFACE_WEBSITE = "website";
export const SURFACE_STREAMLIT = "streamlit";

export type Surface = typeof SURFACE_WEBSITE | typeof SURFACE_STREAMLIT;
