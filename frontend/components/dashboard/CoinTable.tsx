'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { fetchCoins } from '@/lib/api'
import { useLivePrices } from '@/hooks/useLivePrices'
import type { CoinData } from '@/lib/types'
import {
  formatPrice,
  formatPercentage,
  formatVolume,
  formatMarketCap,
} from '@/lib/utils'
import { Search, ChevronUp, ChevronDown, ExternalLink } from 'lucide-react'

type SortKey = keyof Pick<
  CoinData,
  | 'price'
  | 'price_change_pct_24h'
  | 'volume_24h'
  | 'market_cap'
  | 'confidence_score'
  | 'volatility_score'
>
type SortDir = 'asc' | 'desc'
type Filter = 'ALL' | 'LONG' | 'SHORT'

const PAGE_SIZE = 50
// Duration must match the CSS flash-green/flash-red animation length in globals.css
const FLASH_DURATION_MS = 900

export function CoinTable() {
  const router = useRouter()
  const [coins, setCoins] = useState<CoinData[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('ALL')
  const [sortKey, setSortKey] = useState<SortKey>('market_cap')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(1)
  const { prices } = useLivePrices()
  const prevPricesRef = useRef<Record<string, number>>({})
  const [flashMap, setFlashMap] = useState<Record<string, 'up' | 'down'>>({})

  useEffect(() => {
    fetchCoins()
      .then(setCoins)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  // Detect price changes and trigger flash
  useEffect(() => {
    const newFlash: Record<string, 'up' | 'down'> = {}
    for (const [sym, price] of Object.entries(prices)) {
      const prev = prevPricesRef.current[sym]
      if (prev !== undefined && prev !== price) {
        newFlash[sym] = price > prev ? 'up' : 'down'
      }
    }
    if (Object.keys(newFlash).length > 0) {
      setFlashMap((prev) => ({ ...prev, ...newFlash }))
      prevPricesRef.current = { ...prevPricesRef.current, ...prices }
      // Remove flash after animation
      setTimeout(() => {
        setFlashMap((prev) => {
          const next = { ...prev }
          for (const k of Object.keys(newFlash)) delete next[k]
          return next
        })
      }, FLASH_DURATION_MS)
    } else {
      prevPricesRef.current = { ...prevPricesRef.current, ...prices }
    }
  }, [prices])

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
    setPage(1)
  }

  const filtered = coins
    .filter((c) => {
      const q = search.toLowerCase()
      return (
        c.symbol.toLowerCase().includes(q) || c.name.toLowerCase().includes(q)
      )
    })
    .filter((c) => filter === 'ALL' || c.signal_status === filter)
    .sort((a, b) => {
      const av = a[sortKey] as number
      const bv = b[sortKey] as number
      return sortDir === 'asc' ? av - bv : bv - av
    })

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ChevronUp className="w-3.5 h-3.5 text-gray-300" />
    return sortDir === 'asc' ? (
      <ChevronUp className="w-3.5 h-3.5 text-blue-500" />
    ) : (
      <ChevronDown className="w-3.5 h-3.5 text-blue-500" />
    )
  }

  const thClass = 'px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide cursor-pointer select-none hover:text-gray-700 whitespace-nowrap'

  return (
    <div className="bg-white rounded-xl border border-gray-200">
      {/* Table header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 border-b border-gray-100">
        <h2 className="text-base font-bold text-gray-900">All Coins</h2>
        <div className="flex gap-2 flex-wrap">
          {/* Signal filter */}
          <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm">
            {(['ALL', 'LONG', 'SHORT'] as Filter[]).map((f) => (
              <button
                key={f}
                onClick={() => { setFilter(f); setPage(1) }}
                className={`px-3 py-1.5 font-medium transition-colors ${
                  filter === f
                    ? f === 'LONG'
                      ? 'bg-emerald-500 text-white'
                      : f === 'SHORT'
                      ? 'bg-red-500 text-white'
                      : 'bg-blue-600 text-white'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1) }}
              className="pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px]">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide w-10">#</th>
              <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Coin</th>
              <th className={thClass} onClick={() => handleSort('price')}>
                <span className="flex items-center gap-1">Price <SortIcon col="price" /></span>
              </th>
              <th className={thClass} onClick={() => handleSort('price_change_pct_24h')}>
                <span className="flex items-center gap-1">24h % <SortIcon col="price_change_pct_24h" /></span>
              </th>
              <th className={thClass} onClick={() => handleSort('volume_24h')}>
                <span className="flex items-center gap-1">Volume <SortIcon col="volume_24h" /></span>
              </th>
              <th className={thClass} onClick={() => handleSort('market_cap')}>
                <span className="flex items-center gap-1">Mkt Cap <SortIcon col="market_cap" /></span>
              </th>
              <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Signal</th>
              <th className={thClass} onClick={() => handleSort('confidence_score')}>
                <span className="flex items-center gap-1">Confidence <SortIcon col="confidence_score" /></span>
              </th>
              <th className={thClass} onClick={() => handleSort('volatility_score')}>
                <span className="flex items-center gap-1">Volatility <SortIcon col="volatility_score" /></span>
              </th>
              <th className="px-3 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading
              ? [...Array(10)].map((_, i) => (
                  <tr key={i}>
                    {[...Array(10)].map((__, j) => (
                      <td key={j} className="px-3 py-3">
                        <div className="h-4 bg-gray-100 rounded animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              : paged.map((coin, idx) => {
                  const livePrice = prices[coin.symbol] ?? prices[`${coin.symbol}USDT`] ?? coin.price
                  const flashClass = flashMap[coin.symbol] === 'up'
                    ? 'flash-green'
                    : flashMap[coin.symbol] === 'down'
                    ? 'flash-red'
                    : ''
                  const changePos = coin.price_change_pct_24h >= 0

                  return (
                    <tr
                      key={coin.symbol}
                      className="hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-3 py-3 text-sm text-gray-400">
                        {(page - 1) * PAGE_SIZE + idx + 1}
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-2.5">
                          {coin.image && (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={coin.image}
                              alt={coin.name}
                              className="w-7 h-7 rounded-full flex-shrink-0"
                            />
                          )}
                          <div>
                            <p className="text-sm font-semibold text-gray-900">{coin.symbol.toUpperCase()}</p>
                            <p className="text-xs text-gray-400">{coin.name}</p>
                          </div>
                        </div>
                      </td>
                      <td className={`px-3 py-3 text-sm font-mono font-medium text-gray-900 ${flashClass}`}>
                        {formatPrice(livePrice)}
                      </td>
                      <td className="px-3 py-3">
                        <span
                          className={`text-sm font-medium ${
                            changePos ? 'text-emerald-600' : 'text-red-600'
                          }`}
                        >
                          {formatPercentage(coin.price_change_pct_24h)}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-sm text-gray-600">
                        {formatVolume(coin.volume_24h)}
                      </td>
                      <td className="px-3 py-3 text-sm text-gray-600">
                        {formatMarketCap(coin.market_cap)}
                      </td>
                      <td className="px-3 py-3">
                        <SignalBadge status={coin.signal_status} />
                      </td>
                      <td className="px-3 py-3">
                        <ConfidenceBadge score={coin.confidence_score} />
                      </td>
                      <td className="px-3 py-3">
                        <VolatilityBadge score={coin.volatility_score} />
                      </td>
                      <td className="px-3 py-3">
                        <Link
                          href={`/coin/${encodeURIComponent(coin.symbol)}`}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
                        >
                          View <ExternalLink className="w-3 h-3" />
                        </Link>
                      </td>
                    </tr>
                  )
                })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
          <p className="text-sm text-gray-500">
            {filtered.length} coins · Page {page} of {totalPages}
          </p>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition-colors"
            >
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg disabled:opacity-40 hover:bg-gray-50 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function SignalBadge({ status }: { status: CoinData['signal_status'] }) {
  if (status === 'LONG') {
    return (
      <span className="inline-flex px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-100 text-emerald-700">
        LONG
      </span>
    )
  }
  if (status === 'SHORT') {
    return (
      <span className="inline-flex px-2 py-0.5 text-xs font-bold rounded-full bg-red-100 text-red-700">
        SHORT
      </span>
    )
  }
  return (
    <span className="inline-flex px-2 py-0.5 text-xs font-semibold rounded-full bg-gray-100 text-gray-500">
      WAIT
    </span>
  )
}

function ConfidenceBadge({ score }: { score: number }) {
  const colorClass =
    score >= 75
      ? 'text-emerald-700 bg-emerald-50'
      : score >= 50
      ? 'text-amber-700 bg-amber-50'
      : 'text-red-700 bg-red-50'
  return (
    <span className={`inline-flex px-2 py-0.5 text-xs font-bold rounded-full ${colorClass}`}>
      {score}%
    </span>
  )
}

function VolatilityBadge({ score }: { score: number }) {
  const colorClass =
    score >= 75
      ? 'text-red-700 bg-red-50'
      : score >= 40
      ? 'text-amber-700 bg-amber-50'
      : 'text-blue-700 bg-blue-50'
  return (
    <span className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${colorClass}`}>
      {score}
    </span>
  )
}
