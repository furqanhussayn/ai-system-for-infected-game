using System;

[Serializable]
public class RegisterBotRequest {
    public string matchId;
    public string botId;
    public int wave;
    public string[] alivePlayers;
    public string[] infectedPlayers;
}

[Serializable]
public class RegisterBotResponse {
    public string botId;
    public string personality;
    public string behaviorMode;
    public string trace;
}

[Serializable]
public class DecideActionRequest {
    public string matchId;
    public string phase;
    public int wave;
    public string botId;
    public string[] infectedPlayers;
    public string[] humanPlayers;
    public int taskProgress;
    public string nearestHuman;
    public string botRoom;
}

[Serializable]
public class DecideActionResponse {
    public string botId;
    public string behaviorMode;
    public string targetRoom;
    public string targetPlayer; // null if none
    public bool shouldChase;
    public string trace;
}

[Serializable]
public class ChatMessage {
    public string sender;
    public string text;
}

[Serializable]
public class RespondRequest {
    public string matchId;
    public string botId;
    public string message;
    public ChatMessage[] recentChat;
    public string[] alivePlayers;
    public string[] infectedPlayers;
}

[Serializable]
public class RespondResponse {
    public string botId;
    public string[] messages;
    public string trace;
}

[Serializable]
public class VoteRequest {
    public string matchId;
    public string botId;
    public string[] alivePlayers;
    public string[] infectedPlayers;
    public ChatMessage[] recentChat;
}

[Serializable]
public class VoteResponse {
    public string botId;
    public string voteTarget;
    public string trace;
}

[Serializable]
public class TraceResponse {
    public TraceEntry[] traces;
}

[Serializable]
public class TraceEntry {
    public string ts;
    public string eventType; // "event"
    public string matchId;
    public string input; // raw JSON string of input
    public string output; // raw JSON string of output
}

// Note: Unity's JsonUtility requires fields (not properties) and simple types/arrays.
// For more advanced JSON handling (lists, nested arrays), consider using Newtonsoft.Json (Json.NET) package.
