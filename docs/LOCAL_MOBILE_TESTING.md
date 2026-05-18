# Local Mobile Testing

## What works and what does not
- `localhost` works only on the same PC that is running the backend.
- Unity on a mobile device cannot use `localhost` to reach your laptop.
- For mobile testing, use either the same WiFi LAN IP or ngrok.

## Option A: Same WiFi + PC local IP
1. Run the backend on your PC.
2. Find your PC IP address on the local network.
3. Use that IP in Unity, for example `http://192.168.1.20:8000`.
4. Make sure the phone and PC are on the same WiFi.
5. If it fails, check Windows Firewall and allow Python/Uvicorn on private networks.

## Option B: ngrok
1. Run the backend on port 8000.
2. Start ngrok:
   ```powershell
   ngrok http 8000
   ```
3. Copy the HTTPS forwarding URL from ngrok.
4. Paste that URL into Unity as the `baseUrl` in `AIDirectorClient`.

## How to run the backend
```powershell
cd "C:\Users\SHAFIN AHMED ABBASI\Downloads\AI BRAIN\team-a-backend"
.\scripts\run_dev.ps1
```

## How to test /health from phone browser
- If using LAN IP: open `http://<PC_LOCAL_IP>:8000/health` on your phone browser.
- If using ngrok: open `https://<your-ngrok-url>/health` on your phone browser.
- Expected response:
  ```json
  {"status":"ok","service":"infected-ai-backend"}
  ```

## Where to paste baseUrl in Unity
- In `AIDirectorClient`, set:
  - `baseUrl = "http://<PC_LOCAL_IP>:8000"` for LAN testing
  - `baseUrl = "https://<ngrok-url>"` for mobile over internet tunneling

## Common firewall problems
- Python/Uvicorn blocked by Windows Firewall.
- Port 8000 blocked on private network profile.
- Phone and PC are not on the same WiFi.
- Using the wrong IP address (public IP instead of LAN IP).
- ngrok URL changed after restart.

## Notes
- Keep the backend rule-based and zero-cost for hackathon testing.
- Use `/docs` in the browser to inspect and try endpoints directly.
