/**
 * Iconos SVG (estilo Feather/Lucide) — sin emojis.
 */
import React from 'react';

const S = ({ size = 18, children, ...p }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...p}>
    {children}
  </svg>
);

export const IcSearch = (p) => <S {...p}><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></S>;
export const IcZap = (p) => <S {...p}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></S>;
export const IcEraser = (p) => <S {...p}><path d="m7 21-4.3-4.3a1 1 0 0 1 0-1.4L15 3a1 1 0 0 1 1.4 0L21 7.6a1 1 0 0 1 0 1.4L12 18" /><path d="M22 21H7" /><path d="m5 11 9 9" /></S>;
export const IcChart = (p) => <S {...p}><line x1="12" y1="20" x2="12" y2="10" /><line x1="18" y1="20" x2="18" y2="4" /><line x1="6" y1="20" x2="6" y2="16" /></S>;
export const IcArchive = (p) => <S {...p}><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><line x1="10" y1="12" x2="14" y2="12" /></S>;
export const IcRefresh = (p) => <S {...p}><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></S>;
export const IcKey = (p) => <S {...p}><path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4" /><path d="m21 2-9.6 9.6" /><circle cx="7.5" cy="15.5" r="5.5" /></S>;
export const IcBook = (p) => <S {...p}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></S>;
export const IcHome = (p) => <S {...p}><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></S>;
export const IcClock = (p) => <S {...p}><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></S>;
export const IcShield = (p) => <S {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></S>;
export const IcCheck = (p) => <S {...p}><polyline points="20 6 9 17 4 12" /></S>;
export const IcCopy = (p) => <S {...p}><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></S>;
export const IcX = (p) => <S {...p}><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></S>;
export const IcDownload = (p) => <S {...p}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></S>;
export const IcTrash = (p) => <S {...p}><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></S>;
export const IcPlay = (p) => <S {...p}><polygon points="5 3 19 12 5 21 5 3" /></S>;
export const IcPause = (p) => <S {...p}><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></S>;
export const IcStop = (p) => <S {...p}><rect x="5" y="5" width="14" height="14" rx="2" /></S>;
export const IcGlobe = (p) => <S {...p}><circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></S>;
export const IcServer = (p) => <S {...p}><rect x="2" y="2" width="20" height="8" rx="2" /><rect x="2" y="14" width="20" height="8" rx="2" /><line x1="6" y1="6" x2="6.01" y2="6" /><line x1="6" y1="18" x2="6.01" y2="18" /></S>;
export const IcCheck2 = (p) => <S {...p}><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></S>;
export const IcRotate = (p) => <S {...p}><path d="M21 2v6h-6" /><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M3 22v-6h6" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /></S>;
