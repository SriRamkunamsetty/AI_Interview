import { logger } from 'firebase-functions'

const defaultQuestionSet = [
  'Tell me about a challenging project you led recently.',
  'How do you prioritize tasks when you have multiple deadlines?',
  'Describe a time you improved the performance of an application.',
]

const fallbackEvaluation = {
  communication: 70,
  technical: 70,
  confidence: 70,
  overall: 70,
  feedback: 'Provide clearer structure and add more detail to your examples.',
}

function extractJson(text: string) {
  const match = text.match(/[\[{][\s\S]*[\]}]/)
  return match ? match[0] : ''
}

async function callOpenAI(prompt: string) {
  const apiKey = process.env.OPENAI_API_KEY
  if (!apiKey) {
    logger.warn('OPENAI_API_KEY is not set')
    return ''
  }

  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL ?? 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: 'You are an interview coach returning JSON only.',
        },
        { role: 'user', content: prompt },
      ],
      temperature: 0.2,
    }),
  })

  if (!response.ok) {
    logger.warn('OpenAI request failed', await response.text())
    return ''
  }

  const data = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>
  }
  return data.choices?.[0]?.message?.content ?? ''
}

async function callGemini(prompt: string) {
  const apiKey = process.env.GEMINI_API_KEY
  if (!apiKey) {
    logger.warn('GEMINI_API_KEY is not set')
    return ''
  }

  const model = process.env.GEMINI_MODEL ?? 'gemini-1.5-flash'
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.2,
          maxOutputTokens: 512,
        },
      }),
    },
  )

  if (!response.ok) {
    logger.warn('Gemini request failed', await response.text())
    return ''
  }

  const data = (await response.json()) as {
    candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>
  }
  return data.candidates?.[0]?.content?.parts?.[0]?.text ?? ''
}

async function callAiProvider(prompt: string) {
  const provider = (process.env.AI_PROVIDER ?? 'openai').toLowerCase()
  const result = provider === 'gemini' ? await callGemini(prompt) : await callOpenAI(prompt)
  return result
}

export async function generateQuestions(role: string, count = 5) {
  const prompt = `Generate ${count} interview questions for a ${role} role. Respond only with JSON array of strings.`
  const raw = await callAiProvider(prompt)
  const extracted = extractJson(raw)
  try {
    const parsed = JSON.parse(extracted) as string[]
    return parsed.length ? parsed : defaultQuestionSet
  } catch (error) {
    logger.warn('Question JSON parse failed', error)
    return defaultQuestionSet
  }
}

export async function evaluateAnswer(question: string, answer: string) {
  const prompt = `Score the answer to the interview question. Return JSON with communication, technical, confidence (0-100) and feedback string.\n\nQuestion: ${question}\nAnswer: ${answer}`
  const raw = await callAiProvider(prompt)
  const extracted = extractJson(raw)
  try {
    const parsed = JSON.parse(extracted) as {
      communication: number
      technical: number
      confidence: number
      feedback: string
    }
    const overall = Math.round(
      (parsed.communication + parsed.technical + parsed.confidence) / 3,
    )
    return {
      ...parsed,
      overall,
    }
  } catch (error) {
    logger.warn('Evaluation JSON parse failed', error)
    return fallbackEvaluation
  }
}
