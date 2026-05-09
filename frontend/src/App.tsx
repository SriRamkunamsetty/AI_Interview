import { useEffect, useMemo, useState } from 'react'
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  getIdTokenResult,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from 'firebase/auth'
import type { User } from 'firebase/auth'
import {
  collection,
  doc,
  onSnapshot,
  orderBy,
  query,
  serverTimestamp,
  setDoc,
  where,
} from 'firebase/firestore'
import { auth, firestore } from './lib/firebase'
import type { InterviewSession } from './lib/types'
import {
  adminDashboardCallable,
  completeSessionCallable,
  createSessionCallable,
  generateQuestionsCallable,
} from './services/functions'
import { uploadUserFile } from './services/storage'

const provider = new GoogleAuthProvider()

const emptyScores = {
  communication: 0,
  technical: 0,
  confidence: 0,
  overall: 0,
}

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [sessions, setSessions] = useState<InterviewSession[]>([])
  const [authError, setAuthError] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('Frontend Engineer')
  const [candidateUid, setCandidateUid] = useState('')
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const [adminStats, setAdminStats] = useState<Record<string, number> | null>(null)

  const sessionQuery = useMemo(() => {
    if (!user) return null
    return query(
      collection(firestore, 'sessions'),
      where('participantUids', 'array-contains', user.uid),
      orderBy('createdAt', 'desc'),
    )
  }, [user])

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (nextUser) => {
      setUser(nextUser)
      setAuthError(null)
      setSessions([])
      setAdminStats(null)
      if (nextUser) {
        const token = await getIdTokenResult(nextUser, true)
        setIsAdmin(Boolean(token.claims.admin))
      } else {
        setIsAdmin(false)
      }
    })

    return () => unsubscribe()
  }, [])

  useEffect(() => {
    if (!sessionQuery) return undefined
    const unsubscribe = onSnapshot(sessionQuery, (snapshot) => {
      const nextSessions = snapshot.docs.map((document) => {
        const data = document.data() as Omit<InterviewSession, 'id'>
        return {
          id: document.id,
          ...data,
        }
      })
      setSessions(nextSessions)
    })
    return () => unsubscribe()
  }, [sessionQuery])

  const handleEmailLogin = async () => {
    setAuthError(null)
    try {
      await signInWithEmailAndPassword(auth, email, password)
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Unable to sign in')
    }
  }

  const handleEmailSignup = async () => {
    setAuthError(null)
    try {
      await createUserWithEmailAndPassword(auth, email, password)
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Unable to sign up')
    }
  }

  const handleGoogleLogin = async () => {
    setAuthError(null)
    try {
      await signInWithPopup(auth, provider)
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Unable to sign in')
    }
  }

  const handleCreateSession = async () => {
    if (!user) return
    setStatus('Creating session...')
    try {
      const response = await createSessionCallable({
        role,
        candidateUid: candidateUid.trim() || undefined,
      })
      const { sessionId } = response.data as { sessionId: string }
      setStatus(`Session created: ${sessionId}`)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Unable to create session')
    }
  }

  const handleGenerateQuestions = async (sessionId: string) => {
    setStatus('Generating questions...')
    try {
      await generateQuestionsCallable({ sessionId })
      setStatus('Questions generated')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Unable to generate questions')
    }
  }

  const handleCompleteSession = async (sessionId: string) => {
    setStatus('Completing session...')
    try {
      await completeSessionCallable({ sessionId })
      setStatus('Session completed')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Unable to complete session')
    }
  }

  const handleResumeUpload = async (file: File, sessionId?: string) => {
    if (!user) return
    setStatus('Uploading resume...')
    setUploadProgress(0)
    try {
      const resumeRef = doc(collection(firestore, 'resumes'))
      const storagePath = `resumes/${user.uid}/${resumeRef.id}-${file.name}`
      const downloadUrl = await uploadUserFile(storagePath, file, setUploadProgress)
      await setDoc(resumeRef, {
        ownerUid: user.uid,
        sessionId: sessionId ?? null,
        fileName: file.name,
        storagePath,
        downloadUrl,
        createdAt: serverTimestamp(),
      })
      setStatus('Resume uploaded')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setUploadProgress(null)
    }
  }

  const handleFetchAdminStats = async () => {
    setStatus('Fetching admin dashboard...')
    try {
      const response = await adminDashboardCallable({})
      setAdminStats(response.data as Record<string, number>)
      setStatus('Admin dashboard refreshed')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Unable to fetch admin stats')
    }
  }

  const handleSignOut = async () => {
    await signOut(auth)
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <div>
            <p className="text-sm font-semibold text-brand-600">AI Interview Platform</p>
            <h1 className="text-2xl font-semibold text-slate-900">
              Firebase-first interview operations console
            </h1>
            <p className="text-sm text-slate-500">
              Real-time sessions, AI evaluation, and secure media storage.
            </p>
          </div>
          {user ? (
            <div className="text-right">
              <p className="text-sm font-medium">{user.email}</p>
              <button
                className="mt-2 rounded-lg border border-slate-200 px-3 py-1 text-sm"
                onClick={handleSignOut}
              >
                Sign out
              </button>
            </div>
          ) : null}
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[320px_1fr]">
        <section className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <h2 className="text-lg font-semibold">Authentication</h2>
            <p className="text-sm text-slate-500">Use Firebase Auth (email or Google).</p>
          </div>
          {!user ? (
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-500">Email</label>
                <input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  placeholder="name@company.com"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-500">Password</label>
                <input
                  value={password}
                  type="password"
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  placeholder="••••••••"
                />
              </div>
              <div className="flex flex-col gap-2">
                <button
                  className="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white"
                  onClick={handleEmailLogin}
                >
                  Sign in
                </button>
                <button
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold"
                  onClick={handleEmailSignup}
                >
                  Create account
                </button>
                <button
                  className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold"
                  onClick={handleGoogleLogin}
                >
                  Sign in with Google
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-xl bg-slate-50 p-4 text-sm">
                <p className="font-semibold">Signed in</p>
                <p className="text-slate-500">{user.uid}</p>
                <p className="mt-2 text-xs text-slate-500">
                  Role: {isAdmin ? 'Admin' : 'Member'}
                </p>
              </div>
            </div>
          )}
          {authError ? <p className="text-sm text-red-500">{authError}</p> : null}
        </section>

        <section className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold">Create a session</h2>
              <p className="text-sm text-slate-500">Use Cloud Functions to create a new session.</p>
              <div className="mt-4 space-y-3">
                <div>
                  <label className="text-xs font-semibold text-slate-500">Role</label>
                  <input
                    value={role}
                    onChange={(event) => setRole(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-500">Candidate UID (optional)</label>
                  <input
                    value={candidateUid}
                    onChange={(event) => setCandidateUid(event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  />
                </div>
                <button
                  className="w-full rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  onClick={handleCreateSession}
                  disabled={!user}
                >
                  Create session
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold">Upload resume</h2>
              <p className="text-sm text-slate-500">
                Store resumes in Firebase Storage and metadata in Firestore.
              </p>
              <div className="mt-4 space-y-3">
                <input
                  type="file"
                  accept=".pdf,.doc,.docx"
                  className="w-full text-sm"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) handleResumeUpload(file)
                  }}
                  disabled={!user}
                />
                {uploadProgress !== null ? (
                  <div className="text-xs text-slate-500">Upload {uploadProgress}%</div>
                ) : null}
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Active sessions</h2>
                <p className="text-sm text-slate-500">Realtime Firestore updates.</p>
              </div>
              <div className="text-xs text-slate-400">{sessions.length} sessions</div>
            </div>
            <div className="mt-4 grid gap-4">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className="rounded-xl border border-slate-200 p-4 transition hover:border-brand-200"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">{session.role}</p>
                      <p className="text-xs text-slate-500">Session ID: {session.id}</p>
                      <p className="text-xs text-slate-500">Status: {session.status}</p>
                    </div>
                    <div className="text-right text-xs text-slate-500">
                      <p>Comm: {session.scoresSummary?.communication ?? emptyScores.communication}</p>
                      <p>Tech: {session.scoresSummary?.technical ?? emptyScores.technical}</p>
                      <p>Conf: {session.scoresSummary?.confidence ?? emptyScores.confidence}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      className="rounded-lg border border-slate-200 px-3 py-1 text-xs"
                      onClick={() => handleGenerateQuestions(session.id)}
                    >
                      Generate questions
                    </button>
                    <button
                      className="rounded-lg border border-slate-200 px-3 py-1 text-xs"
                      onClick={() => handleCompleteSession(session.id)}
                    >
                      Complete session
                    </button>
                  </div>
                </div>
              ))}
              {!sessions.length ? (
                <div className="rounded-xl border border-dashed border-slate-200 p-6 text-sm text-slate-500">
                  Sign in to create or view interview sessions.
                </div>
              ) : null}
            </div>
          </div>

          {isAdmin ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Admin dashboard</h2>
                  <p className="text-sm text-slate-500">Aggregate metrics from Cloud Functions.</p>
                </div>
                <button
                  className="rounded-lg border border-slate-200 px-3 py-1 text-xs"
                  onClick={handleFetchAdminStats}
                >
                  Refresh
                </button>
              </div>
              <div className="mt-4 grid gap-2 text-sm text-slate-600">
                {adminStats ? (
                  Object.entries(adminStats).map(([key, value]) => (
                    <div key={key} className="flex items-center justify-between">
                      <span className="capitalize">{key.replace(/([A-Z])/g, ' $1')}</span>
                      <span className="font-semibold text-slate-900">{value}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-slate-500">No metrics loaded yet.</p>
                )}
              </div>
            </div>
          ) : null}

          {status ? (
            <div className="rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-700">
              {status}
            </div>
          ) : null}
        </section>
      </main>
    </div>
  )
}

export default App
