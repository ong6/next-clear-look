import type { SVGProps } from "react";

const paths: Record<string, React.ReactNode> = {
  aperture: (
    <>
      <path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  satellite: (
    <>
      <path d="m9 9 3-3 3 3-3 3-3-3Z" />
      <path d="m5 6 4 3-4 3-3-3 3-3Zm14 0-4 3 4 3 3-3-3-3ZM12 12v6" />
      <circle cx="12" cy="20" r="1.2" />
    </>
  ),
  play: <path d="m9 7 8 5-8 5V7Z" />,
  pause: (
    <>
      <path d="M9 7v10M15 7v10" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="1.5" />
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
    </>
  ),
  north: (
    <>
      <path d="m12 3 5 17-5-3-5 3 5-17Z" />
      <path d="M12 17V8" />
    </>
  ),
  reset: (
    <>
      <path d="M5 7V3m0 0h4M5 3l3 3a7 7 0 1 1-2 9" />
    </>
  ),
  close: <path d="m6 6 12 12M18 6 6 18" />,
  evidence: (
    <>
      <path d="M5 5h5M14 5h5v5M19 14v5h-5M10 19H5v-5" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  layers: (
    <>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5M3 16l9 5 9-5" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6M12 7h.01" />
    </>
  ),
  arrow: <path d="m15 18-6-6 6-6" />,
  chevron: <path d="m8 10 4 4 4-4" />,
  copy: (
    <>
      <rect x="8" y="8" width="11" height="11" rx="1" />
      <path d="M16 8V5H5v11h3" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" />
    </>
  ),
  draw: (
    <>
      <path d="M5 18 18 5M14 5h4v4" />
      <path d="M4 14v6h6" />
    </>
  ),
};

export function Icon({ name, ...props }: { name: keyof typeof paths } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="square"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
