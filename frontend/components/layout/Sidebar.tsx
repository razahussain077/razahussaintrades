'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Home,
  TrendingUp,
  Wallet,
  Settings,
  BarChart2,
} from 'lucide-react'

const navItems = [
  { href: '/', label: 'Dashboard', icon: Home },
  { href: '/signals', label: 'Signals', icon: TrendingUp },
  { href: '/portfolio', label: 'Portfolio', icon: Wallet },
  { href: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col fixed top-0 left-0 h-full w-60 bg-white border-r border-gray-200 z-30">
        {/* Brand */}
        <div className="flex items-center gap-2.5 px-5 py-5 border-b border-gray-100">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <BarChart2 className="w-5 h-5 text-white" />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-900 leading-none">SMC Bot</p>
            <p className="text-xs text-gray-500 mt-0.5">Signal Dashboard</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
              >
                <Icon className={`w-4.5 h-4.5 flex-shrink-0 ${active ? 'text-blue-600' : 'text-gray-400'}`} />
                {label}
              </Link>
            )
          })}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-100">
          <p className="text-xs text-gray-400">© {new Date().getFullYear()} SMC Bot</p>
          <p className="text-xs text-gray-400 mt-0.5">v1.0.0</p>
        </div>
      </aside>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 z-30 flex">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = href === '/' ? pathname === '/' : pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={`flex-1 flex flex-col items-center py-2 gap-0.5 text-xs font-medium transition-colors ${
                active ? 'text-blue-600' : 'text-gray-500'
              }`}
            >
              <Icon className="w-5 h-5" />
              {label}
            </Link>
          )
        })}
      </nav>
    </>
  )
}
