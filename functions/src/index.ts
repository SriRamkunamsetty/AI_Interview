import { initializeApp } from 'firebase-admin/app'
import { getAuth } from 'firebase-admin/auth'
import { FieldValue, getFirestore } from 'firebase-admin/firestore'
import { logger, setGlobalOptions } from 'firebase-functions'
import { HttpsError, onCall } from 'firebase-functions/v2/https'
import { onDocumentCreated, onDocumentUpdated } from 'firebase-functions/v2/firestore'
import { onSchedule } from 'firebase-functions/v2/scheduler'
import { evaluateAnswer, generateQuestions as generateQuestionSet } from './ai'
import { requireAdmin, requireAuth } from './auth'

setGlobalOptions({ region: 'us-central1' })

initializeApp()

const firestore = getFirestore()
const auth = getAuth()

export const createSession = onCall(async (request) => {
  const user = requireAuth(request)
  const { candidateUid, role } = request.data as {
    candidateUid?: string
    role?: string
  }

  const sessionRef = firestore.collection('sessions').doc()
  const participantUids = [user.uid]
  if (candidateUid && candidateUid !== user.uid) {
    participantUids.push(candidateUid)
  }

  await sessionRef.set({
    createdBy: user.uid,
    candidateUid: candidateUid ?? null,
    participantUids,
    role: role ?? 'Interview Session',
    status: 'pending',
    createdAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
    scoresSummary: {
      communication: 0,
      technical: 0,
      confidence: 0,
      overall: 0,
    },
    scoreTotals: {
      communication: 0,
      technical: 0,
      confidence: 0,
    },
    scoreCount: 0,
  })

  await firestore.doc(`users/${user.uid}`).set(
    {
      lastActiveAt: FieldValue.serverTimestamp(),
    },
    { merge: true },
  )

  return { sessionId: sessionRef.id }
})

export const generateQuestions = onCall(async (request) => {
  const user = requireAuth(request)
  const { sessionId } = request.data as { sessionId?: string }
  if (!sessionId) {
    throw new HttpsError('invalid-argument', 'sessionId is required.')
  }

  const sessionRef = firestore.doc(`sessions/${sessionId}`)
  const sessionSnap = await sessionRef.get()
  if (!sessionSnap.exists) {
    throw new HttpsError('not-found', 'Session not found.')
  }

  const session = sessionSnap.data() as { participantUids?: string[]; role?: string }
  if (!session.participantUids?.includes(user.uid) && !user.token?.admin) {
    throw new HttpsError('permission-denied', 'Not authorized for this session.')
  }

  const questions = await generateQuestionSet(session.role ?? 'Interview', 5)
  const batch = firestore.batch()
  questions.forEach((question, index) => {
    const questionRef = sessionRef.collection('questions').doc()
    batch.set(questionRef, {
      text: question,
      order: index + 1,
      createdAt: FieldValue.serverTimestamp(),
      createdBy: user.uid,
    })
  })

  await batch.commit()
  await sessionRef.set({ updatedAt: FieldValue.serverTimestamp() }, { merge: true })

  return { count: questions.length }
})

export const submitAnswer = onCall(async (request) => {
  const user = requireAuth(request)
  const { sessionId, questionId, answer } = request.data as {
    sessionId?: string
    questionId?: string
    answer?: string
  }

  if (!sessionId || !answer) {
    throw new HttpsError('invalid-argument', 'sessionId and answer are required.')
  }

  const sessionRef = firestore.doc(`sessions/${sessionId}`)
  const sessionSnap = await sessionRef.get()
  if (!sessionSnap.exists) {
    throw new HttpsError('not-found', 'Session not found.')
  }

  const session = sessionSnap.data() as { participantUids?: string[] }
  if (!session.participantUids?.includes(user.uid) && !user.token?.admin) {
    throw new HttpsError('permission-denied', 'Not authorized for this session.')
  }

  const answerRef = sessionRef.collection('answers').doc()
  await answerRef.set({
    sessionId,
    questionId: questionId ?? null,
    answer,
    createdBy: user.uid,
    createdAt: FieldValue.serverTimestamp(),
    status: 'submitted',
  })

  await sessionRef.set({ updatedAt: FieldValue.serverTimestamp() }, { merge: true })

  return { answerId: answerRef.id }
})

export const completeSession = onCall(async (request) => {
  const user = requireAuth(request)
  const { sessionId } = request.data as { sessionId?: string }
  if (!sessionId) {
    throw new HttpsError('invalid-argument', 'sessionId is required.')
  }

  const sessionRef = firestore.doc(`sessions/${sessionId}`)
  const sessionSnap = await sessionRef.get()
  if (!sessionSnap.exists) {
    throw new HttpsError('not-found', 'Session not found.')
  }

  const session = sessionSnap.data() as { participantUids?: string[] }
  if (!session.participantUids?.includes(user.uid) && !user.token?.admin) {
    throw new HttpsError('permission-denied', 'Not authorized for this session.')
  }

  await sessionRef.update({
    status: 'completed',
    completedAt: FieldValue.serverTimestamp(),
    updatedAt: FieldValue.serverTimestamp(),
  })

  return { status: 'completed' }
})

export const adminDashboard = onCall(async (request) => {
  requireAdmin(request)
  const [sessions, users, resumes] = await Promise.all([
    firestore.collection('sessions').count().get(),
    firestore.collection('users').count().get(),
    firestore.collection('resumes').count().get(),
  ])

  return {
    sessions: sessions.data().count,
    users: users.data().count,
    resumes: resumes.data().count,
  }
})

export const setAdminRole = onCall(async (request) => {
  requireAdmin(request)
  const { uid, admin } = request.data as { uid?: string; admin?: boolean }
  if (!uid) {
    throw new HttpsError('invalid-argument', 'uid is required.')
  }
  await auth.setCustomUserClaims(uid, { admin: Boolean(admin) })
  return { uid, admin: Boolean(admin) }
})

export const onAnswerCreated = onDocumentCreated(
  'sessions/{sessionId}/answers/{answerId}',
  async (event) => {
    const snapshot = event.data
    if (!snapshot) return

    const answer = snapshot.data() as {
      answer?: string
      questionId?: string
      createdBy?: string
    }

    const sessionId = event.params.sessionId as string
    const sessionRef = firestore.doc(`sessions/${sessionId}`)
    const sessionSnap = await sessionRef.get()
    if (!sessionSnap.exists) {
      logger.warn('Session missing for answer evaluation', { sessionId })
      return
    }

    const questionsSnap = answer.questionId
      ? await sessionRef.collection('questions').doc(answer.questionId).get()
      : null

    const questionText = questionsSnap?.data()?.text ?? 'Interview question'
    const evaluation = await evaluateAnswer(questionText, answer.answer ?? '')

    await snapshot.ref.update({
      evaluation,
      status: 'scored',
      scoredAt: FieldValue.serverTimestamp(),
    })

    await firestore.runTransaction(async (transaction) => {
      const sessionSnapshot = await transaction.get(sessionRef)
      const sessionData = sessionSnapshot.data() as {
        scoreTotals?: {
          communication?: number
          technical?: number
          confidence?: number
        }
        scoreCount?: number
      }

      const totals = {
        communication: sessionData?.scoreTotals?.communication ?? 0,
        technical: sessionData?.scoreTotals?.technical ?? 0,
        confidence: sessionData?.scoreTotals?.confidence ?? 0,
      }
      const count = sessionData?.scoreCount ?? 0
      const nextTotals = {
        communication: totals.communication + evaluation.communication,
        technical: totals.technical + evaluation.technical,
        confidence: totals.confidence + evaluation.confidence,
      }
      const nextCount = count + 1
      const summary = {
        communication: Math.round(nextTotals.communication / nextCount),
        technical: Math.round(nextTotals.technical / nextCount),
        confidence: Math.round(nextTotals.confidence / nextCount),
      }
      const overall = Math.round(
        (summary.communication + summary.technical + summary.confidence) / 3,
      )

      transaction.update(sessionRef, {
        scoreTotals: nextTotals,
        scoreCount: nextCount,
        scoresSummary: {
          ...summary,
          overall,
        },
        updatedAt: FieldValue.serverTimestamp(),
      })
    })
  },
)

export const onSessionCompleted = onDocumentUpdated(
  'sessions/{sessionId}',
  async (event) => {
    const before = event.data?.before.data()
    const after = event.data?.after.data()

    if (!before || !after) return
    if (before.status === after.status || after.status !== 'completed') return

    await event.data?.after.ref.set(
      {
        reportStatus: 'ready',
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    )
  },
)

export const aggregateAnalytics = onSchedule('every 6 hours', async () => {
  const [sessions, users, resumes] = await Promise.all([
    firestore.collection('sessions').count().get(),
    firestore.collection('users').count().get(),
    firestore.collection('resumes').count().get(),
  ])

  await firestore.doc('analytics/summary').set({
    sessions: sessions.data().count,
    users: users.data().count,
    resumes: resumes.data().count,
    updatedAt: FieldValue.serverTimestamp(),
  })
})
