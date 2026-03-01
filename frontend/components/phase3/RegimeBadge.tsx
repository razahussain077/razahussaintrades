'use client'

interface RegimeBadgeProps {
  regime?: string
  label?: string
  emoji?: string
  compact?: boolean
}

const REGIME_STYLES: Record<string, string> = {
  trending: 'bg-blue-100 text-blue-700',
  ranging: 'bg-gray-100 text-gray-600',
  volatile: 'bg-orange-100 text-orange-700',
  squeeze: 'bg-purple-100 text-purple-700',
}

export function RegimeBadge({ regime = 'ranging', label, emoji, compact = false }: RegimeBadgeProps) {
  const style = REGIME_STYLES[regime] ?? REGIME_STYLES.ranging
  const emojiMap: Record<string, string> = {
    trending: '📈',
    ranging: '↔️',
    volatile: '🌊',
    squeeze: '💤',
  }
  const displayEmoji = emoji ?? emojiMap[regime] ?? '↔️'
  const displayLabel = label ?? regime.toUpperCase()

  if (compact) {
    return (
      <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs font-medium ${style}`}>
        <span>{displayEmoji}</span>
        <span>{displayLabel}</span>
      </span>
    )
  }

  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium ${style}`}>
      <span>{displayEmoji}</span>
      <span>{displayLabel}</span>
    </span>
  )
}
