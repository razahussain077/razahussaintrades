export function formatPrice(price: number): string {
  if (price === 0) return '$0.00'
  if (price >= 1000) {
    return '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  if (price >= 1) {
    return '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
  }
  if (price >= 0.01) {
    return '$' + price.toFixed(4)
  }
  return '$' + price.toFixed(8)
}

export function formatVolume(volume: number): string {
  if (volume >= 1e12) return `$${(volume / 1e12).toFixed(2)}T`
  if (volume >= 1e9) return `$${(volume / 1e9).toFixed(2)}B`
  if (volume >= 1e6) return `$${(volume / 1e6).toFixed(2)}M`
  if (volume >= 1e3) return `$${(volume / 1e3).toFixed(2)}K`
  return `$${volume.toFixed(2)}`
}

export function formatMarketCap(cap: number): string {
  return formatVolume(cap)
}

export function formatPercentage(pct: number): string {
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

export function getPktTime(): string {
  return new Date().toLocaleTimeString('en-US', {
    timeZone: 'Asia/Karachi',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
}

export function getPktDateTime(): string {
  return new Date().toLocaleString('en-US', {
    timeZone: 'Asia/Karachi',
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function getSignalColor(type: 'LONG' | 'SHORT'): string {
  return type === 'LONG' ? '#10b981' : '#ef4444'
}

export function getConfidenceColor(score: number): string {
  if (score >= 75) return '#10b981'
  if (score >= 50) return '#f59e0b'
  return '#ef4444'
}

export function getRiskColor(risk: number): string {
  if (risk < 3) return '#10b981'
  if (risk <= 5) return '#f59e0b'
  return '#ef4444'
}

export function timeAgo(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function clsx(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ')
}
