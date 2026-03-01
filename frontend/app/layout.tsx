import type { Metadata } from 'next'
import './globals.css'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'

export const metadata: Metadata = {
  title: 'SMC Bot – Crypto Trading Signals',
  description: 'Smart Money Concept crypto trading signal dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <div className="flex min-h-screen">
          {/* Sidebar */}
          <Sidebar />

          {/* Main area */}
          <div className="flex flex-col flex-1 min-w-0 ml-0 md:ml-60">
            {/* Fixed header */}
            <Header />

            {/* Page content */}
            <main className="flex-1 mt-16 p-4 md:p-6 overflow-auto">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  )
}
