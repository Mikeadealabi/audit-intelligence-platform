import type { CSSProperties } from "react";

type IconProps = { size?: number; className?: string; style?: CSSProperties };

const base = (size = 16) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none" as const,
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export function ShieldIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <path d="M12 2l8 3.5v5.3c0 5-3.4 8.9-8 10.2-4.6-1.3-8-5.2-8-10.2V5.5L12 2z" />
      <path d="M8.5 12.2l2.3 2.3 4.7-4.9" />
    </svg>
  );
}

export function GridIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
    </svg>
  );
}

export function UploadIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <path d="M12 16V4" />
      <path d="M7 9l5-5 5 5" />
      <path d="M4 16v3a2 2 0 002 2h12a2 2 0 002-2v-3" />
    </svg>
  );
}

export function AlertIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <path d="M10.3 3.9L2.6 17a1.6 1.6 0 001.4 2.4h16a1.6 1.6 0 001.4-2.4L13.7 3.9a1.6 1.6 0 00-2.8 0z" />
      <path d="M12 9.5v4" />
      <path d="M12 16.8h.01" />
    </svg>
  );
}

export function DocIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <path d="M7 3h7l5 5v12a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h6" />
    </svg>
  );
}

export function SparkleIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style} fill="currentColor" stroke="none">
      <path d="M12 2.5l1.7 4.7 4.8 1.8-4.8 1.8L12 15.5l-1.7-4.7-4.8-1.8 4.8-1.8L12 2.5z" />
      <path d="M19.2 14l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9.9-2.4z" opacity="0.7" />
    </svg>
  );
}

export function ArrowRightIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <path d="M5 12h14" />
      <path d="M13 6l6 6-6 6" />
    </svg>
  );
}

export function CheckCircleIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 12.3l2.3 2.3 4.7-4.9" />
    </svg>
  );
}

export function ClockIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </svg>
  );
}

export function LockIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <rect x="5" y="10.5" width="14" height="9.5" rx="1.8" />
      <path d="M8 10.5V7.5a4 4 0 018 0v3" />
    </svg>
  );
}

export function FileSearchIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <path d="M7 3h7l5 5v12a1 1 0 01-1 1h-5" />
      <path d="M14 3v5h5" />
      <circle cx="8" cy="16" r="3" />
      <path d="M10.3 18.3L12.5 20.5" />
    </svg>
  );
}

export function BarChartIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <path d="M4 20V10" />
      <path d="M11 20V4" />
      <path d="M18 20v-7" />
      <path d="M3 20h18" />
    </svg>
  );
}

export function ActivityIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <path d="M3 12h4l2.5-7 4 14 2.5-7H21" />
    </svg>
  );
}

export function BuildingIcon({ size, className, style }: IconProps) {
  return (
    <svg {...base(size)} className={className} style={style}>
      <rect x="4" y="3" width="11" height="18" rx="1" />
      <path d="M8 7h3M8 11h3M8 15h3" />
      <path d="M15 21v-6h4a1 1 0 011 1v5" />
    </svg>
  );
}
