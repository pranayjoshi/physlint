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
    default: "Physlint Evidence Atlas",
    template: "%s · Physlint Evidence Atlas",
  },
  description: "Reproducible evidence for robot dataset and recording health.",
  openGraph: {
    title: "Physlint Evidence Atlas",
    description: "Know your robot data before training.",
    type: "website",
    images: [{ url: "/physlint-observatory-social.png", width: 1731, height: 909 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Physlint Evidence Atlas",
    description: "Reproducible validation evidence for LeRobot, MCAP, and ROS 2.",
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
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(c,l,a,r,i,t,y){
        c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
        t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
        y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
    })(window, document, "clarity", "script", "y9khep9f7w");`,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
