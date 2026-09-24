/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "false" switches data services from src/mock to the YieldLens API. */
  readonly VITE_DEMO_MODE?: string;
  /** API origin + prefix; defaults to same-origin "/api". */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
