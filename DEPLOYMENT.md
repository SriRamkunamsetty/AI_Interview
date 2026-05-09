# Firebase Deployment Guide

## Overview
The platform deploys to Firebase Hosting (frontend) and Firebase Cloud Functions (backend). Firestore and Storage are the primary data stores.

## Prerequisites
- Firebase CLI installed (`npm install -g firebase-tools`)
- Firebase project created (dev/stage/prod)
- Local `.env` files configured

## Firebase setup
```bash
firebase login
firebase use --add
```

## Deploy hosting + functions
```bash
firebase deploy --only hosting,functions
```

## Deploy per environment
```bash
firebase use <project-id>
firebase deploy --only hosting,functions
```

## Recommended Firebase settings
- Enable App Check for production apps
- Configure Authentication providers (Email/Password + Google)
- Create Firestore indexes from `firestore.indexes.json`
- Apply security rules from `firestore.rules` and `storage.rules`

## Migration notes
Legacy Render/Vercel deployment is deprecated. The `backend/` and `forenten/` folders are retained for reference only.
