import { HttpsError, CallableRequest } from 'firebase-functions/v2/https'

export function requireAuth(request: CallableRequest) {
  if (!request.auth) {
    throw new HttpsError('unauthenticated', 'Authentication required.')
  }
  return request.auth
}

export function requireAdmin(request: CallableRequest) {
  const auth = requireAuth(request)
  if (!auth.token?.admin) {
    throw new HttpsError('permission-denied', 'Admin privileges required.')
  }
  return auth
}
