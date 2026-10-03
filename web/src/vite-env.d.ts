/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_NCL_MOCK?: string;
  readonly VITE_NCL_TEST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  __ncl?: {
    setTime: (isoTime: string) => void;
    pause: () => void;
  };
  __nclPerf?: {
    fps: number;
    p10Fps: number;
    longestTaskMs: number;
  };
}
