using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

public class AIDirectorClient : MonoBehaviour {
    public string baseUrl = "http://localhost:8000";

    // Example: register bot after takeover
    public void RegisterBot() {
        var req = new RegisterBotRequest {
            matchId = "ROOM123",
            botId = "player_2",
            wave = 1,
            alivePlayers = new string[] {"player_1","player_2","player_3","player_4"},
            infectedPlayers = new string[] {"player_2"}
        };
        StartCoroutine(PostJson("/register_bot", JsonUtility.ToJson(req), (response) => {
            Debug.Log("RegisterBot response: " + response);
            // TODO: parse JsonUtility.FromJson<RegisterBotResponse>(response)
            // Save personality & behaviorMode to local bot controller
        }));
    }

    public void DecideAction() {
        var req = new DecideActionRequest {
            matchId = "ROOM123",
            phase = "exploration",
            wave = 1,
            botId = "player_2",
            infectedPlayers = new string[] {"player_2"},
            humanPlayers = new string[] {"player_1","player_3","player_4"},
            taskProgress = 3,
            nearestHuman = "player_3",
            botRoom = "Electrical"
        };
        StartCoroutine(PostJson("/decide_action", JsonUtility.ToJson(req), (response) => {
            Debug.Log("DecideAction response: " + response);
            // TODO: parse DecideActionResponse and update BotMovement
            // If shouldChase -> connect to BotMovement.chase(targetPlayer)
        }));
    }

    public void SendChatToBot(string message) {
        var chatReq = new RespondRequest {
            matchId = "ROOM123",
            botId = "player_2",
            message = message,
            recentChat = new ChatMessage[] { new ChatMessage { sender = "player_1", text = message } },
            alivePlayers = new string[] {"player_1","player_2","player_3","player_4"},
            infectedPlayers = new string[] {"player_2"}
        };
        StartCoroutine(PostJson("/respond", JsonUtility.ToJson(chatReq), (response) => {
            Debug.Log("Respond: " + response);
            // TODO: parse RespondResponse; enqueue messages into MeetingChatUI
        }));
    }

    public void RequestBotVote() {
        var v = new VoteRequest {
            matchId = "ROOM123",
            botId = "player_2",
            alivePlayers = new string[] {"player_1","player_2","player_3","player_4"},
            infectedPlayers = new string[] {"player_2"},
            recentChat = new ChatMessage[] {
                new ChatMessage { sender = "player_1", text = "player 2 is sus" }
            }
        };
        StartCoroutine(PostJson("/vote", JsonUtility.ToJson(v), (response) => {
            Debug.Log("Vote response: " + response);
            // TODO: parse VoteResponse and instruct VotingUI to select that player card
        }));
    }

    IEnumerator PostJson(string path, string json, System.Action<string> onComplete) {
        var url = baseUrl + path;
        using (UnityWebRequest www = new UnityWebRequest(url, "POST")) {
            byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(json);
            www.uploadHandler = new UploadHandlerRaw(bodyRaw);
            www.downloadHandler = new DownloadHandlerBuffer();
            www.SetRequestHeader("Content-Type", "application/json");
            yield return www.SendWebRequest();

            if (www.result == UnityWebRequest.Result.ConnectionError || www.result == UnityWebRequest.Result.ProtocolError) {
                Debug.LogError($"AI request error: {www.error}");
                onComplete?.Invoke(null);
            } else {
                onComplete?.Invoke(www.downloadHandler.text);
            }
        }
    }

    // Helper MonoBehaviour hooks where Team B should connect to their systems:
    // - After infection takeover in game logic -> call RegisterBot()
    // - BotMovement: use DecideAction() periodically (20-30s) and handle returned behaviorMode/targetRoom
    // - MeetingChatUI: when a chat message mentions a bot -> call SendChatToBot(message) and display returned messages
    // - VotingUI: at voting start -> call RequestBotVote() and apply returned voteTarget into the UI
}
