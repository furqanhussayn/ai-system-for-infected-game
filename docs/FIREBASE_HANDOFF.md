# Firebase Handoff

Team A ships a lightweight Firebase handoff package so Team B can wire Unity to Realtime Database without needing backend source changes.

## What Team B needs

- Firebase project ID
- Realtime Database URL
- Android `google-services.json` for Unity handoff
- Firebase Unity SDK in the Unity project

## Setup steps

1. Create a Firebase project.
2. Enable Realtime Database.
3. Use test or hackathon rules for development.
4. Add an Android app in Firebase.
5. Download `google-services.json`.
6. Place it in `firebase/unity_config/android/google-services.json` for handoff.
7. Team B imports the Firebase Unity SDK.
8. Team B copies `google-services.json` into Unity `Assets` during integration.
9. Team B uses the Realtime Database URL in Unity config.
10. Do not commit private keys or service account files.

## Provided files

- `firebase/realtime-database-rules.json`
- `firebase/sample_match_ROOM123.json`
- `firebase/unity_config/android/.gitkeep`
- `firebase/unity_config/ios/.gitkeep`

## Notes

- The repository never stores real Google service files.
- The sample match JSON is only a structural handoff example.