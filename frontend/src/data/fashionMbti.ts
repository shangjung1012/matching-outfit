export type MbtiAxisKey = 'C' | 'S' | 'B' | 'I' | 'M' | 'O' | 'N' | 'V'

export type MbtiRawScores = Record<MbtiAxisKey, number>

export interface FashionMbtiAnswer {
  questionId: number
  optionId: 'A' | 'B' | 'C' | 'D'
}

export interface FashionMbtiOption {
  id: 'A' | 'B' | 'C' | 'D'
  label: string
  scores: Partial<Record<MbtiAxisKey, number>>
  image?: string
}

export interface FashionMbtiQuestion {
  id: number
  prompt: string
  visual?: boolean
  options: FashionMbtiOption[]
}

export interface FashionMbtiType {
  code: string
  name: string
  representative: {
    name: string
  }
  description: string
}

export interface FashionMbtiResult {
  code: string
  name: string
  representative: FashionMbtiType['representative']
  description: string
  keywords: string[]
  scores: {
    comfort: number
    style: number
    budget: number
    invest: number
    modest: number
    open: number
    neutral: number
    vivid: number
  }
  raw: MbtiRawScores
  answers: FashionMbtiAnswer[]
  completedAt: string
}

export const MBTI_AXES = [
  {
    id: 'wear',
    title: '穿著取向',
    a: 'C' as const,
    b: 'S' as const,
    aLabel: '舒適派',
    bLabel: '造型派',
  },
  {
    id: 'price',
    title: '消費取向',
    a: 'B' as const,
    b: 'I' as const,
    aLabel: '實惠派',
    bLabel: '高價派',
  },
  {
    id: 'coverage',
    title: '露膚取向',
    a: 'M' as const,
    b: 'O' as const,
    aLabel: '包覆派',
    bLabel: '露膚派',
  },
  {
    id: 'color',
    title: '色彩取向',
    a: 'N' as const,
    b: 'V' as const,
    aLabel: '素色派',
    bLabel: '彩色派',
  },
] as const

const AXIS_KEYWORD: Record<MbtiAxisKey, string> = {
  C: '舒適',
  S: '造型',
  B: '實惠',
  I: '高價',
  M: '包覆',
  O: '露膚',
  N: '素色',
  V: '彩色',
}

const questionImage = (fileName: string) =>
  `${import.meta.env.BASE_URL}images/fashion-mbti/${fileName}`

/**
 * 十題設計：
 * - 8 題生活情境 + 2 題圖片題。
 * - 每個選項通常會影響 2–3 個維度。
 * - 主要維度給 2–3 分，次要維度多半只給 1 分，避免某個情境把其他軸帶偏。
 * - 選項文字刻意不直接使用「舒適、高價、包覆、彩色」等分類詞。
 */
export const MBTI_QUESTIONS: FashionMbtiQuestion[] = [
  {
    id: 1,
    prompt: '早上出門才發現外面下大雨，你今天本來想穿一雙不太耐水、但跟整套最搭的鞋，你會怎麼處理？',
    options: [
      {
        id: 'A',
        label: '照原本穿，頂多小心一點走；今天這套就是少了那雙鞋會差很多',
        scores: { S: 3, I: 1 },
      },
      {
        id: 'B',
        label: '換成另一雙顏色和輪廓差不多的鞋，整體不要差太多就好',
        scores: { S: 1, N: 1, B: 1 },
      },
      {
        id: 'C',
        label: '換成平常最好走、也不怕濕的那雙，反正下雨天先顧實際',
        scores: { C: 2, B: 1 },
      },
      {
        id: 'D',
        label: '如果只是上課或買東西，直接穿最省事的鞋，襪子不要濕比較重要',
        scores: { C: 3, B: 1, M: 1 },
      },
    ],
  },
  {
    id: 2,
    prompt: '朋友臨時約你 30 分鐘後去吃飯，你回家只有一點時間可以換衣服，你通常會？',
    options: [
      {
        id: 'A',
        label: '把身上的衣服整理一下就出門，頂多換鞋或加件外套',
        scores: { C: 2, B: 1, N: 1 },
      },
      {
        id: 'B',
        label: '拿一套自己常穿、幾乎不會出錯的搭配，省時間也有精神',
        scores: { C: 1, N: 2, M: 1 },
      },
      {
        id: 'C',
        label: '會換一件比較有造型的上衣或下身，至少讓今天看起來不像隨便出門',
        scores: { S: 2, O: 1, V: 1 },
      },
      {
        id: 'D',
        label: '還是會重新搭一套，鞋、包或配件也會一起看，晚個幾分鐘可以接受',
        scores: { S: 3, I: 1, V: 1 },
      },
    ],
  },
  {
    id: 3,
    prompt: '逛街時你看到一件很喜歡的外套，試穿也很好看，但價格大概是你平常買外套的兩倍，你會？',
    options: [
      {
        id: 'A',
        label: '先拍照記下來，回家找類似版型或同色系的替代款',
        scores: { B: 3, N: 1 },
      },
      {
        id: 'B',
        label: '先離開去逛其他店，如果還一直想到它再回來決定',
        scores: { B: 1, I: 1, C: 1 },
      },
      {
        id: 'C',
        label: '看材質、做工和自己會不會常穿；如果都不錯，我可以接受超一點預算',
        scores: { I: 2, C: 1, M: 1 },
      },
      {
        id: 'D',
        label: '如果穿上真的很有感、而且別的地方找不到類似的，我大概會直接買',
        scores: { I: 3, S: 1, V: 1 },
      },
    ],
  },
  {
    id: 4,
    prompt: '你有 3,000 元想補幾件新衣服，以下哪種購物結果會讓你最滿意？',
    options: [
      {
        id: 'A',
        label: '買到 3–4 件都能常穿的單品，價格不要太高，彼此也好搭',
        scores: { B: 3, N: 1, C: 1 },
      },
      {
        id: 'B',
        label: '買兩件平常會穿的，再留一點預算給一件比較特別的',
        scores: { B: 1, V: 1, S: 1 },
      },
      {
        id: 'C',
        label: '買一件真的很喜歡、質料和版型都好的，再搭一件基本款',
        scores: { I: 2, N: 1, S: 1 },
      },
      {
        id: 'D',
        label: '如果那件主角單品真的夠好看，三千幾乎都花在它身上也可以',
        scores: { I: 3, S: 2 },
      },
    ],
  },
  {
    id: 5,
    prompt: '週末白天很熱，但你要去的咖啡廳冷氣通常很強，接著還要在外面走一陣子，你會比較想穿？',
    options: [
      {
        id: 'A',
        label: '薄長褲＋有袖上衣，再帶一件很輕的外套，冷熱都比較好調整',
        scores: { M: 3, C: 2, N: 1 },
      },
      {
        id: 'B',
        label: '短袖＋長褲，真的冷再撐一下，至少不用一直拿外套',
        scores: { M: 1, C: 1, B: 1 },
      },
      {
        id: 'C',
        label: '短袖＋長下身，再帶件薄外套，熱的時候可以脫掉外套，冷的時候全身也不會太冷',
        scores: { O: 2, C: 1, V: 1 },
      },
      {
        id: 'D',
        label: '短袖＋短下身，冷氣房再套襯衫或外套，整套比較有層次',
        scores: { O: 3, S: 1, V: 1 },
      },
    ],
  },
  {
    id: 6,
    prompt: '朋友約你去海邊待一整天，會拍照、吃飯，也可能走很久。你比較可能帶哪一套？',
    options: [
      {
        id: 'A',
        label: '寬鬆上衣＋長褲或長裙＋好走的鞋，曬太陽和走路都比較安心',
        scores: { M: 3, C: 2, N: 1 },
      },
      {
        id: 'B',
        label: 'T-shirt＋短褲，再帶一件薄襯衫，活動方便也不會太露',
        scores: { O: 1, C: 2, B: 1 },
      },
      {
        id: 'C',
        label: '背心或短版上衣＋短褲或短裙，照片好看、天氣熱也比較舒服',
        scores: { O: 2, S: 1, V: 1 },
      },
      {
        id: 'D',
        label: '會特別準備一套平常比較少穿的度假 Look，顏色、配件都一起搭好',
        scores: { O: 2, S: 2, V: 2, I: 1 },
      },
    ],
  },
  {
    id: 7,
    prompt: '你要參加一個沒有硬性 Dress Code 的生日聚會，下面哪種準備方式最像你？',
    options: [
      {
        id: 'A',
        label: '穿自己平常最好看的固定組合，乾淨俐落就夠了',
        scores: { N: 2, C: 1, B: 1 },
      },
      {
        id: 'B',
        label: '用原本的基本款，換一個顏色比較亮的包、鞋或配件',
        scores: { V: 2, B: 1, S: 1 },
      },
      {
        id: 'C',
        label: '會挑一件平常比較少穿、剪裁或露膚比例比較特別的單品',
        scores: { S: 2, O: 2, I: 1 },
      },
      {
        id: 'D',
        label: '會把聚會當成一個可以認真搭配的場合，整套想得比平常完整',
        scores: { S: 3, I: 1, V: 1, O: 1 },
      },
    ],
  },
  {
    id: 8,
    prompt: '旅行前你發現行李重量快超標，只能再帶一套衣服。你最後會塞哪一套進去？',
    options: [
      {
        id: 'A',
        label: '最舒服、最不挑場合的那套，就算照片看起來普通一點也沒關係',
        scores: { C: 3, B: 1, N: 1, M: 1 },
      },
      {
        id: 'B',
        label: '黑白或大地色的基本款，能跟已經帶的鞋和外套互相搭',
        scores: { N: 3, B: 1, M: 1 },
      },
      {
        id: 'C',
        label: '一套顏色比較亮、拍照會很好看的，反正旅行本來就想跟平常不一樣',
        scores: { V: 3, S: 1, O: 1 },
      },
      {
        id: 'D',
        label: '那套平常捨不得穿、質感最好的一套；都出門旅行了就想穿得完整',
        scores: { I: 2, S: 2, M: 1 },
      },
    ],
  },
  {
    id: 9,
    prompt: '假設你是女生，四套都很適合你的身形，也都在你的預算內，週末逛街你最想直接穿哪一套？',
    visual: true,
    options: [
      {
        id: 'A',
        label: '黑白灰為主、長下身、鞋子也很簡單的一套',
        scores: { N: 3, M: 2, C: 1 },
        image: questionImage('8A.jpg'),
      },
      {
        id: 'B',
        label: '米色跟丹寧色為主，版型輕鬆，帶一個小配色重點',
        scores: { N: 1, V: 1, C: 2, M: 1 },
        image: questionImage('8B.jpg'),
      },
      {
        id: 'C',
        label: '基本色搭一個明顯亮色，比例比較俐落、露膚也多一點',
        scores: { V: 2, O: 2, S: 1 },
        image: questionImage('8C.jpg'),
      },
      {
        id: 'D',
        label: '兩到三個顏色一起出現，剪裁和配件都比較有存在感',
        scores: { V: 3, S: 2, O: 1, I: 1 },
        image: questionImage('8D.jpg'),
      },
    ],
  },
  {
    id: 10,
    prompt: '以下四種款式的上衣，你第一眼最容易被哪個吸引？',
    visual: true,
    options: [
      {
        id: 'A',
        label: '黑或灰，正常版型，領口和袖長都比較保守',
        scores: { N: 3, M: 2, B: 1 },
        image: questionImage('10A.png'),
      },
      {
        id: 'B',
        label: '米白或深藍，材質舒服，版型有一點變化但很好日常穿',
        scores: { N: 2, C: 2, I: 1 },
        image: questionImage('10B.png'),
      },
      {
        id: 'C',
        label: '藍綠粉等有顏色的版本，剪裁稍微俐落或短一點',
        scores: { V: 2, O: 1, S: 1 },
        image: questionImage('10C.png'),
      },
      {
        id: 'D',
        label: '最亮或最少見的顏色，設計感也最強，就算不好搭也會想試',
        scores: { V: 3, S: 2, I: 1, O: 1 },
        image: questionImage('10D.png'),
      },
    ],
  },
  {
    id: 11,
    prompt: '假設你是男生，平常去上班或者上課時，你會最常穿哪一種穿搭？',
    visual: true,
    options: [
      {
        id: 'A',
        label: '舒服、包覆、素色',
        scores: { C: 3, M: 2, N: 2, B: 1 },
        image: questionImage('11A.jpg'),
      },
      {
        id: 'B',
        label: '基本款之上多一點材質跟細節',
        scores: { B: 2, S: 1, C: 1, N: 1 },
        image: questionImage('11B.jpg'),
      },
      {
        id: 'C',
        label: '高質感、精緻剪裁',
        scores: { I: 3, S: 1, M: 1, N: 1 },
        image: questionImage('11C.jpg'),
      },
      {
        id: 'D',
        label: '強造型感',
        scores: { S: 3, V: 2, O: 1, I: 2 },
        image: questionImage('11D.jpg'),
      },
    ],
  }
]

export const MBTI_TYPES: Record<string, FashionMbtiType> = {
  CBMN: {
    code: 'CBMN',
    name: '自在基本者',
    representative: { name: '極簡日常派' },
    description: '你重視舒服與實穿，也喜歡價格合理、包覆感足夠的素色單品。衣櫃不用複雜，穿起來自在、好搭最重要。',
  },
  CBMV: {
    code: 'CBMV',
    name: '舒服玩色者',
    representative: { name: '彩色休閒派' },
    description: '舒服與實惠是基本條件，但你不想讓衣櫃只有黑白灰。比起特殊剪裁，你更願意用顏色替日常穿搭加一點趣味。',
  },
  CBON: {
    code: 'CBON',
    name: '清爽簡約者',
    representative: { name: '輕盈基本派' },
    description: '你喜歡舒服、價格好入手的單品，也偏好比較清爽的露膚比例；配色則保持乾淨簡單，整體看起來自然不費力。',
  },
  CBOV: {
    code: 'CBOV',
    name: '陽光玩色者',
    representative: { name: '夏日活力派' },
    description: '你喜歡舒服、好入手、清爽又有顏色的衣服。短版、短下身與亮色都能成為日常，不需要昂貴也能穿得很有精神。',
  },
  CIMN: {
    code: 'CIMN',
    name: '質感安定者',
    representative: { name: '高質感基本派' },
    description: '舒服仍然重要，但遇到材質、做工或版型真的好的單品，你願意多花一點。偏愛包覆、素色與能長期穿著的高質感基本款。',
  },
  CIMV: {
    code: 'CIMV',
    name: '質感配色者',
    representative: { name: '精品休閒派' },
    description: '你願意為舒適與品質付出更高預算，也不排斥鮮明色彩。整體包覆感偏高，但會用漂亮色彩讓高質感單品不顯無聊。',
  },
  CION: {
    code: 'CION',
    name: '輕奢清爽者',
    representative: { name: '度假質感派' },
    description: '你願意為真正舒服、好看的衣服多花一點，也偏好較輕盈的露膚感。配色通常簡潔，靠材質與剪裁營造乾淨的高級感。',
  },
  CIOV: {
    code: 'CIOV',
    name: '亮彩享受者',
    representative: { name: '精品度假派' },
    description: '舒適、品質、清爽與色彩你都想要。你願意為喜歡的單品提高預算，也很適合亮色、短版與度假感較強的穿搭。',
  },

  SBMN: {
    code: 'SBMN',
    name: '聰明造型者',
    representative: { name: '高 CP 造型派' },
    description: '你重視整體好看，但不一定要靠高價完成造型。偏好包覆與素色，因此更講究比例、搭配與版型，用有限預算穿出完成度。',
  },
  SBMV: {
    code: 'SBMV',
    name: '平價吸睛者',
    representative: { name: '彩色混搭派' },
    description: '你喜歡有造型感，也很會在預算內找到亮點。包覆度偏高，但不怕用鮮明顏色、撞色或彩色配件讓整套更有記憶點。',
  },
  SBON: {
    code: 'SBON',
    name: '俐落辣感者',
    representative: { name: '都會俐落派' },
    description: '你重視造型與身體線條，也懂得控制預算。比起繽紛配色，你更偏好素色、露膚或俐落剪裁，把重點放在輪廓本身。',
  },
  SBOV: {
    code: 'SBOV',
    name: '大膽潮玩者',
    representative: { name: '街頭亮眼派' },
    description: '你喜歡造型、露膚與鮮明色彩，但不認為好看一定要昂貴。你很適合透過平價單品快速嘗試醒目的新 Look。',
  },
  SIMN: {
    code: 'SIMN',
    name: '低調精品者',
    representative: { name: '極簡精品派' },
    description: '你願意為造型與品質投資，但不需要靠大量露膚或鮮豔顏色吸引注意。剪裁、布料與細節才是你真正重視的地方。',
  },
  SIMV: {
    code: 'SIMV',
    name: '彩色收藏者',
    representative: { name: '藝術精品派' },
    description: '你重視造型，也願意為設計與品質買單。雖然偏好較有包覆感的衣服，但色彩可以很大膽，像把穿搭當成收藏與創作。',
  },
  SION: {
    code: 'SION',
    name: '精緻線條者',
    representative: { name: '都會精品派' },
    description: '你願意投資在有造型感的單品，也偏好露出適度肌膚或身體線條。配色多半乾淨克制，讓剪裁與比例成為主角。',
  },
  SIOV: {
    code: 'SIOV',
    name: '華麗主角者',
    representative: { name: '高調時尚派' },
    description: '你願意為造型投入預算，也不怕露膚與鮮明色彩。對你而言穿搭就是完整表達，值得用有存在感的單品把造型做到位。',
  },
}

function emptyScores(): MbtiRawScores {
  return { C: 0, S: 0, B: 0, I: 0, M: 0, O: 0, N: 0, V: 0 }
}

function optionOf(answer: FashionMbtiAnswer) {
  const question = MBTI_QUESTIONS.find((row) => row.id === answer.questionId)
  return question?.options.find((option) => option.id === answer.optionId) ?? null
}

/** 平手時，回頭找最後一題真正拉開該維度的答案。 */
function resolveSide(
  answers: FashionMbtiAnswer[],
  raw: MbtiRawScores,
  a: MbtiAxisKey,
  b: MbtiAxisKey,
): MbtiAxisKey {
  if (raw[a] !== raw[b]) return raw[a] > raw[b] ? a : b

  for (let index = answers.length - 1; index >= 0; index -= 1) {
    const scores = optionOf(answers[index])?.scores
    if (!scores) continue

    const left = scores[a] ?? 0
    const right = scores[b] ?? 0
    if (left !== right) return left > right ? a : b
  }

  return a
}

function share(left: number, right: number): number {
  const total = left + right
  if (!total) return 50
  return Math.round((left / total) * 100)
}

export function computeMbtiResult(answers: FashionMbtiAnswer[]): FashionMbtiResult {
  const raw = emptyScores()

  for (const answer of answers) {
    const option = optionOf(answer)
    if (!option) continue

    for (const [key, points] of Object.entries(option.scores)) {
      raw[key as MbtiAxisKey] += points ?? 0
    }
  }

  const code = MBTI_AXES.map((axis) => resolveSide(answers, raw, axis.a, axis.b)).join('')
  const type = MBTI_TYPES[code] ?? MBTI_TYPES.CBMN

  const comfort = share(raw.C, raw.S)
  const budget = share(raw.B, raw.I)
  const modest = share(raw.M, raw.O)
  const neutral = share(raw.N, raw.V)

  // 取偏離 50% 最多的三個維度，作為結果頁的 Style DNA 關鍵字。
  const leftPercentages = [comfort, budget, modest, neutral]
  const keywords = MBTI_AXES.map((axis, index) => {
    const leftPct = leftPercentages[index]
    const dominant = leftPct >= 50 ? axis.a : axis.b

    return {
      keyword: AXIS_KEYWORD[dominant],
      gap: Math.abs(leftPct - 50),
      index,
    }
  })
    .sort((left, right) => right.gap - left.gap || left.index - right.index)
    .slice(0, 3)
    .map((row) => row.keyword)

  return {
    code,
    name: type.name,
    representative: type.representative,
    description: type.description,
    keywords,
    scores: {
      comfort,
      style: 100 - comfort,
      budget,
      invest: 100 - budget,
      modest,
      open: 100 - modest,
      neutral,
      vivid: 100 - neutral,
    },
    raw,
    answers,
    completedAt: new Date().toISOString(),
  }
}

// ---- 本機儲存（結果與作答進度） ----

interface StoredState {
  result: FashionMbtiResult | null
  progress: FashionMbtiAnswer[]
}

const storageKey = (userKey: string) => `fashion-mbti:${userKey}`

export function loadMbtiState(userKey: string): StoredState {
  try {
    const raw = window.localStorage.getItem(storageKey(userKey))
    if (!raw) return { result: null, progress: [] }

    const parsed = JSON.parse(raw) as Partial<StoredState>
    return {
      result: parsed.result ?? null,
      progress: Array.isArray(parsed.progress) ? parsed.progress : [],
    }
  } catch {
    return { result: null, progress: [] }
  }
}

export function saveMbtiState(userKey: string, state: StoredState): void {
  try {
    window.localStorage.setItem(storageKey(userKey), JSON.stringify(state))
  } catch {
  }
}
