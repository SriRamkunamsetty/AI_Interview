import { httpsCallable } from 'firebase/functions'
import { functions } from '../lib/firebase'

export const createSessionCallable = httpsCallable(functions, 'createSession')
export const generateQuestionsCallable = httpsCallable(functions, 'generateQuestions')
export const submitAnswerCallable = httpsCallable(functions, 'submitAnswer')
export const completeSessionCallable = httpsCallable(functions, 'completeSession')
export const adminDashboardCallable = httpsCallable(functions, 'adminDashboard')
export const setAdminRoleCallable = httpsCallable(functions, 'setAdminRole')
