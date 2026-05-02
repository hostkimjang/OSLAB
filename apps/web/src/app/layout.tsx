import "./styles.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "oslab control",
  description: "OS/VM validation dashboard",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
