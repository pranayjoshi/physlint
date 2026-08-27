import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Physlint Observatory",
    template: "%s · Physlint Observatory",
  },
  description: "Transparent robot dataset and recording health evidence.",
  openGraph: {
    title: "Physlint Observatory",
    description: "Know your robot data before it trains your model.",
    type: "website",
    images: [{ url: "/physlint-observatory-social.png", width: 1731, height: 909 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Physlint Observatory",
    description: "Open validation evidence for LeRobot, MCAP, and ROS 2.",
    images: ["/physlint-observatory-social.png"],
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
