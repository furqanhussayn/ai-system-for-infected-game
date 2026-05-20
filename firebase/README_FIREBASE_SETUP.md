# Firebase Setup

1. Create a Firebase project.
2. Enable Realtime Database.
3. Use test or hackathon rules during development.
4. Add an Android app.
5. Download `google-services.json`.
6. Place it in `firebase/unity_config/android/google-services.json` for handoff.
7. Team B imports the Firebase Unity SDK.
8. Team B copies `google-services.json` into Unity `Assets`.
9. Team B uses the Realtime Database URL in Unity config.
10. Do not commit private keys, service account files, or secrets.