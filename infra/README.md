# Firebase Infrastructure

This folder documents Firebase configuration for the AI Interview Platform.

## Included assets
- `firebase.json`: Hosting + Functions configuration.
- `firestore.rules` / `storage.rules`: Security rules.
- `firestore.indexes.json`: Composite indexes for session analytics.
- `.firebaserc`: Project mappings for dev/stage/prod.

## Local workflows
1. `firebase login`
2. `firebase use --add`
3. `firebase emulators:start`
4. `firebase deploy --only hosting,functions`
