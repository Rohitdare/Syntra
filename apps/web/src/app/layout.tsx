import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Research Desk",
  description: "Multi-agent research assistant",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
