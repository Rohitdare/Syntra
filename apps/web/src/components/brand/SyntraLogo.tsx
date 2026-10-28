"use client";

import React from "react";
import Image from "next/image";

export interface SyntraLogoProps {
  /**
   * "full" displays the S-mark and "Syntra" wordmark.
   * "mark" displays only the S-mark and star.
   */
  variant?: "full" | "mark";
  /**
   * Accessible description for screen readers.
   * Defaults to "Syntra". Ignored if decorative is true.
   */
  accessibleLabel?: string;
  /**
   * If true, hides from accessibility tree (alt="", aria-hidden="true").
   */
  decorative?: boolean;
  /**
   * Optional custom CSS class.
   */
  className?: string;
  /**
   * Target height in pixels (width will scale proportionately).
   * Default: 32px for full wordmark, 28px for mark.
   */
  height?: number;
}

/**
 * Official Syntra Logo Component.
 * 
 * Renders the authentic mark and wordmark extracted directly from the
 * Syntra Brand Identity Guidelines, supporting both Light and Dark themes.
 */
export function SyntraLogo({
  variant = "full",
  accessibleLabel = "Syntra",
  decorative = false,
  className = "",
  height,
}: SyntraLogoProps) {
  const altText = decorative ? "" : accessibleLabel;
  const isMark = variant === "mark";

  // Aspect ratios based on extracted high-res source bounds:
  // Full logo: 518 x 133 (~3.89 : 1)
  // Mark only: 118 x 132 (~0.89 : 1)
  const defaultHeight = height || (isMark ? 28 : 26);
  const width = isMark
    ? Math.round(defaultHeight * (118 / 132))
    : Math.round(defaultHeight * (518 / 133));

  const darkSrc = isMark ? "/brand/syntra-mark-dark.png" : "/brand/syntra-logo-dark.png";
  const lightSrc = isMark ? "/brand/syntra-mark-light.png" : "/brand/syntra-logo-light.png";

  return (
    <div
      className={`inline-flex items-center select-none ${className}`}
      aria-hidden={decorative ? "true" : undefined}
    >
      {/* Light theme logo (dark pixels on light canvas) */}
      <Image
        src={darkSrc}
        alt={altText}
        width={width}
        height={defaultHeight}
        unoptimized
        priority
        className="block dark:hidden object-contain"
        style={{ height: `${defaultHeight}px`, width: "auto" }}
      />
      {/* Dark theme logo (light pixels on dark canvas) */}
      <Image
        src={lightSrc}
        alt={altText}
        width={width}
        height={defaultHeight}
        unoptimized
        priority
        className="hidden dark:block object-contain"
        style={{ height: `${defaultHeight}px`, width: "auto" }}
      />
    </div>
  );
}
