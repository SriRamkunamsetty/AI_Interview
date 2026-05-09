export type SessionStatus = 'pending' | 'active' | 'completed'

export interface SessionScoreSummary {
  communication: number
  technical: number
  confidence: number
  overall: number
}

export interface InterviewSession {
  createdBy: string
  candidateUid?: string | null
  participantUids: string[]
  role?: string
  status: SessionStatus
  createdAt?: string
  updatedAt?: string
  completedAt?: string
  scoresSummary?: SessionScoreSummary
}

export interface InterviewAnswer {
  sessionId: string
  questionId?: string | null
  answer: string
  createdBy: string
  createdAt?: string
  status?: 'submitted' | 'scored'
}

export interface ResumeMetadata {
  ownerUid: string
  sessionId?: string | null
  fileName: string
  storagePath: string
  downloadUrl: string
  createdAt?: string
}
