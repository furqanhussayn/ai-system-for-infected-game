using System;
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

[Serializable]
public class TeamAApiClient
{
    public string baseUrl = "http://127.0.0.1:8000";
    public int timeoutSeconds = 8;

    public TeamAApiClient(string baseUrl)
    {
        this.baseUrl = baseUrl;
    }

    public async Task<string> Health()
    {
        return await GetTextAsync("/health");
    }

    public async Task<string> RegisterBot(RegisterBotRequest request)
    {
        return await PostJsonAsync("/register_bot", request);
    }

    public async Task<string> UnregisterBot(UnregisterBotRequest request)
    {
        return await PostJsonAsync("/unregister_bot", request);
    }

    public async Task<string> DecideAction(DecideActionRequest request)
    {
        return await PostJsonAsync("/decide_action", request);
    }

    public async Task<string> Respond(RespondRequest request)
    {
        return await PostJsonAsync("/respond", request);
    }

    public async Task<string> Vote(VoteRequest request)
    {
        return await PostJsonAsync("/vote", request);
    }

    public async Task<string> GetTrace(string matchId)
    {
        return await GetTextAsync($"/trace/{matchId}");
    }

    private async Task<string> GetTextAsync(string path)
    {
        using (var request = UnityWebRequest.Get(baseUrl + path))
        {
            request.timeout = timeoutSeconds;
            var operation = request.SendWebRequest();
            while (!operation.isDone)
            {
                await Task.Yield();
            }
            if (request.result != UnityWebRequest.Result.Success)
            {
                throw new Exception(request.error);
            }
            return request.downloadHandler.text;
        }
    }

    private async Task<string> PostJsonAsync(string path, object body)
    {
        var json = JsonUtility.ToJson(body);
        var bytes = Encoding.UTF8.GetBytes(json);
        using (var request = new UnityWebRequest(baseUrl + path, UnityWebRequest.kHttpVerbPOST))
        {
            request.timeout = timeoutSeconds;
            request.uploadHandler = new UploadHandlerRaw(bytes);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            var operation = request.SendWebRequest();
            while (!operation.isDone)
            {
                await Task.Yield();
            }
            if (request.result != UnityWebRequest.Result.Success)
            {
                throw new Exception(request.error);
            }
            return request.downloadHandler.text;
        }
    }
}

[Serializable]
public class RegisterBotRequest
{
    public string matchId;
    public string botId;
    public string botName;
    public int wave;
    public int cycle;
    public string phase;
    public List<string> alivePlayers;
    public List<string> humanPlayers;
    public List<string> infectedPlayers;
    public int taskProgress;
}

[Serializable]
public class RegisterBotResponse
{
    public bool ok;
    public string botId;
    public string personality;
    public string behaviorMode;
    public string trace;
}

[Serializable]
public class UnregisterBotRequest
{
    public string matchId;
    public string botId;
    public string reason;
}

[Serializable]
public class UnregisterBotResponse
{
    public bool ok;
    public string botId;
    public string trace;
}

[Serializable]
public class DecideActionRequest
{
    public string matchId;
    public string phase;
    public int wave;
    public int cycle;
    public string botId;
    public string botName;
    public List<string> infectedPlayers;
    public List<string> humanPlayers;
    public List<string> alivePlayers;
    public int taskProgress;
    public string nearestHuman;
    public string botRoom;
    public string nearestHumanRoom;
    public float secondsSinceLastSeenHuman;
    public bool isFinalChase;
}

[Serializable]
public class DecideActionResponse
{
    public string botId;
    public string behaviorMode;
    public string targetRoom;
    public string targetPlayer;
    public bool shouldChase;
    public int nextDecisionInSeconds;
    public string trace;
}

[Serializable]
public class ChatMessageDto
{
    public string sender;
    public string senderName;
    public string text;
}

[Serializable]
public class RespondRequest
{
    public string matchId;
    public string phase;
    public int wave;
    public int cycle;
    public string botId;
    public string botName;
    public string personality;
    public string message;
    public ChatMessageDto latestMessage;
    public List<ChatMessageDto> recentChat;
    public List<string> alivePlayers;
    public List<string> humanPlayers;
    public List<string> infectedPlayers;
    public bool simulateDelay;
}

[Serializable]
public class RespondResponse
{
    public string botId;
    public bool respond;
    public List<string> messages;
    public float typingDelaySeconds;
    public float secondMessageDelaySeconds;
    public string trace;
}

[Serializable]
public class VoteRequest
{
    public string matchId;
    public string phase;
    public int wave;
    public int cycle;
    public string botId;
    public string botName;
    public List<string> alivePlayers;
    public List<string> humanPlayers;
    public List<string> infectedPlayers;
    public List<ChatMessageDto> recentChat;
}

[Serializable]
public class VoteResponse
{
    public string botId;
    public string voteTarget;
    public string reason;
    public string trace;
}

[Serializable]
public class TraceEntry
{
    public string ts;
    public string eventType;
    public string action;
    public string matchId;
    public string botId;
    public string input;
    public string output;
    public string trace;
    public string source;
}

[Serializable]
public class TraceResponse
{
    public string matchId;
    public int count;
    public List<TraceEntry> traces;
}