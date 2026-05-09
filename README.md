# AI Interview Platform (Firebase-first)

A scalable AI-powered interview platform built on Firebase Hosting, Firestore, Storage, and Cloud Functions. The architecture prioritizes real-time updates, secure media handling, and AI evaluation workflows.

## Architecture snapshot
- **Frontend**: React + Vite + Tailwind (Firebase Hosting)
- **Backend**: Firebase Cloud Functions (HTTP + background triggers)
- **Database**: Firestore (native mode)
- **Storage**: Firebase Storage (resumes, recordings, profile images, reports)
- **Auth**: Firebase Auth (email/password + Google + admin custom claims)
- **AI**: Gemini/OpenAI via secure Cloud Functions

## Repository layout
```
frontend/   # React + Vite client
functions/  # Firebase Cloud Functions (TypeScript)
shared/     # Shared types and schemas
infra/      # Firebase configuration docs
backend/    # Legacy FastAPI backend (deprecated)
forenten/   # Legacy static frontend (deprecated)
```

## Local development
1. Install dependencies:
   ```bash
   npm --prefix frontend install
   npm --prefix functions install
   ```
2. Configure environment variables:
   - `frontend/.env.example`
   - `functions/.env.example`
3. Run locally:
   ```bash
   firebase emulators:start
   npm --prefix frontend run dev
   ```

## Deployment (Firebase)
```bash
firebase deploy --only hosting,functions
```

## Legacy stack
The original FastAPI + MongoDB + Socket.IO implementation is preserved under `backend/` and `forenten/` for reference during migration. New features should be implemented in the Firebase-first stack.
