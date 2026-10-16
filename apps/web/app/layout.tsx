import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { AppSidebar } from "@/components/sidebar/app-sidebar";
import { MobileNav } from "@/components/sidebar/mobile-nav";
import { SidebarContent } from "@/components/sidebar/sidebar-content";
import { cn } from "@/lib/utils";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "Chattie",
  description: "Chat with the Chattie assistant",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={cn("font-sans", geist.variable)}>
      <body className="flex h-dvh bg-background text-foreground antialiased">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <MobileNav>
            <SidebarContent />
          </MobileNav>
          <main className="min-h-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
