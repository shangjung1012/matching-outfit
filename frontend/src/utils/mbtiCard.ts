import type { FashionMbtiResult } from '../types'

/**
 * 分享圖以 canvas 直接繪製，不用 html-to-image / html2canvas：
 * 不必多裝相依套件，輸出尺寸固定，也不會踩到外部圖片的 CORS 問題。
 */
export const CARD_WIDTH = 1080
export const CARD_HEIGHT = 1350

const PAPER = '#f2f0e9'
const INK = '#202723'
const GREEN = '#245a45'
const MUTED = '#7c837a'
const RULE = '#cdd0c6'
const TRACK = '#e0e2da'

const SERIF = '"Noto Serif TC", "Songti TC", Georgia, "Times New Roman", serif'
const SANS = 'Inter, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", system-ui, sans-serif'

const CLOSING_MARKS = new Set(['，', '。', '、', '；', '：', '？', '！', '）', '」', '』', '…'])

function drawTracked(
  context: CanvasRenderingContext2D,
  text: string,
  centerX: number,
  y: number,
  spacing: number,
): void {
  const characters = [...text]
  const width = characters.reduce(
    (total, character) => total + context.measureText(character).width + spacing,
    -spacing,
  )
  const previousAlign = context.textAlign
  context.textAlign = 'left'
  let cursor = centerX - width / 2
  for (const character of characters) {
    context.fillText(character, cursor, y)
    cursor += context.measureText(character).width + spacing
  }
  context.textAlign = previousAlign
}

/** 以字為單位斷行，但把連續的英數視為一個不可拆的詞。 */
function wrapText(context: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const tokens = text.match(/[A-Za-z0-9]+|[^A-Za-z0-9]/g) ?? []
  const lines: string[] = []
  let line = ''
  for (const token of tokens) {
    const candidate = line + token
    if (line && context.measureText(candidate).width > maxWidth && !CLOSING_MARKS.has(token)) {
      lines.push(line)
      line = token.trim()
      continue
    }
    line = candidate
  }
  if (line) lines.push(line)
  return lines
}

/**
 * 英文名字取字首（最多兩個字），中文風格短語（如「極簡日常派」）取第一個字，
 * 避免把詞中夾雜的英文縮寫（如「高 CP 造型派」）誤判成字首。
 */
function monogram(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return ''
  const words = trimmed.split(/\s+/).filter(Boolean)
  if (words.every((word) => /^[A-Za-z]/.test(word))) {
    return words.slice(0, 2).map((word) => word[0].toUpperCase()).join('')
  }
  return [...trimmed][0] ?? ''
}

interface BarRow {
  left: string
  right: string
  leftPct: number
}

export async function renderMbtiCard(
  canvas: HTMLCanvasElement,
  result: FashionMbtiResult,
): Promise<void> {
  const context = canvas.getContext('2d')
  if (!context) return
  // 字型還沒載入時畫出來會是 fallback 字體，等一下再畫。
  await document.fonts?.ready?.catch?.(() => undefined)

  canvas.width = CARD_WIDTH
  canvas.height = CARD_HEIGHT
  context.clearRect(0, 0, CARD_WIDTH, CARD_HEIGHT)
  context.fillStyle = PAPER
  context.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT)

  context.strokeStyle = RULE
  context.lineWidth = 2
  context.strokeRect(36, 36, CARD_WIDTH - 72, CARD_HEIGHT - 72)

  context.textAlign = 'center'
  context.textBaseline = 'alphabetic'

  context.fillStyle = MUTED
  context.font = `600 22px ${SANS}`
  drawTracked(context, 'FASHION MBTI', CARD_WIDTH / 2, 136, 11)

  context.fillStyle = INK
  context.font = `700 168px ${SERIF}`
  drawTracked(context, result.code, CARD_WIDTH / 2, 316, 16)

  context.fillStyle = GREEN
  context.font = `700 58px ${SANS}`
  context.fillText(result.name, CARD_WIDTH / 2, 396)

  context.strokeStyle = RULE
  context.lineWidth = 1
  context.beginPath()
  context.moveTo(CARD_WIDTH / 2 - 110, 446)
  context.lineTo(CARD_WIDTH / 2 + 110, 446)
  context.stroke()

  context.fillStyle = '#e5e9e1'
  context.beginPath()
  context.arc(CARD_WIDTH / 2, 528, 46, 0, Math.PI * 2)
  context.fill()
  context.fillStyle = GREEN
  context.font = `600 34px ${SERIF}`
  context.fillText(monogram(result.representative.name), CARD_WIDTH / 2, 541)

  context.fillStyle = MUTED
  context.font = `500 22px ${SANS}`
  drawTracked(context, '風格參照', CARD_WIDTH / 2, 612, 4)
  context.fillStyle = INK
  context.font = `600 34px ${SANS}`
  context.fillText(result.representative.name, CARD_WIDTH / 2, 658)

  context.fillStyle = '#4c554e'
  context.font = `400 31px ${SANS}`
  const lines = wrapText(context, result.description, 780).slice(0, 3)
  lines.forEach((line, index) => {
    context.fillText(line, CARD_WIDTH / 2, 734 + index * 52)
  })

  const rows: BarRow[] = [
    { left: '舒適派', right: '造型派', leftPct: result.scores.comfort },
    { left: '實惠派', right: '高價派', leftPct: result.scores.budget },
    { left: '包覆派', right: '露膚派', leftPct: result.scores.modest },
    { left: '素色派', right: '彩色派', leftPct: result.scores.neutral },
  ]

  const barLeft = 108
  const barRight = CARD_WIDTH - 108
  const barWidth = barRight - barLeft
  rows.forEach((row, index) => {
    const top = 906 + index * 74
    const leftLeads = row.leftPct >= 50

    context.textAlign = 'left'
    context.font = `${leftLeads ? 700 : 400} 26px ${SANS}`
    context.fillStyle = leftLeads ? INK : MUTED
    context.fillText(leftLeads ? `${row.left} ${row.leftPct}%` : row.left, barLeft, top)

    context.textAlign = 'right'
    context.font = `${leftLeads ? 400 : 700} 26px ${SANS}`
    context.fillStyle = leftLeads ? MUTED : INK
    context.fillText(
      leftLeads ? row.right : `${100 - row.leftPct}% ${row.right}`,
      barRight,
      top,
    )

    context.fillStyle = TRACK
    context.fillRect(barLeft, top + 18, barWidth, 10)
    context.fillStyle = GREEN
    const filled = Math.round((barWidth * row.leftPct) / 100)
    context.fillRect(leftLeads ? barLeft : barLeft + filled, top + 18, leftLeads ? filled : barWidth - filled, 10)
  })

  context.strokeStyle = RULE
  context.beginPath()
  context.moveTo(barLeft, 1236)
  context.lineTo(barRight, 1236)
  context.stroke()

  context.textAlign = 'left'
  context.fillStyle = MUTED
  context.font = `500 24px ${SANS}`
  context.fillText('#YourStyleDNA', barLeft, 1286)

  context.textAlign = 'right'
  context.fillStyle = INK
  context.font = `700 22px ${SANS}`
  context.fillText('MATCHING OUTFIT', barRight, 1286)
}

function toBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('無法產生圖片'))
    }, 'image/png')
  })
}

/** 手機支援時走系統分享，其餘情況直接下載 PNG。 */
export async function saveMbtiCard(canvas: HTMLCanvasElement, code: string): Promise<'shared' | 'downloaded'> {
  const blob = await toBlob(canvas)
  const fileName = `fashion-mbti-${code}.png`
  const file = new File([blob], fileName, { type: 'image/png' })

  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: `Fashion MBTI ${code}` })
      return 'shared'
    } catch (reason) {
      // 使用者取消分享就不要再自動下載一次。
      if (reason instanceof DOMException && reason.name === 'AbortError') return 'shared'
    }
  }

  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return 'downloaded'
}
