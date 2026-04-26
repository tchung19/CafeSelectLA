import { Geist } from "next/font/google";
import "./globals.css";

const geist = Geist({ subsets: ["latin"] });

export const metadata = {
  title: "CafeSelect",
  description: "Find cafes in LA by what actually matters — outlets, noise level, hours, vibe.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={`${geist.className} bg-white text-gray-900 antialiased`}>
        {children}
      </body>
    </html>
  );
}
