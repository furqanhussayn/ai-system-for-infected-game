from src.core import config

print('AI_MODE=', config.AI_MODE)
print('LLM_PROVIDER=', config.LLM_PROVIDER)
print('GROQ_API_KEY set=', bool(config.GROQ_API_KEY))
print('GEMINI_API_KEY set=', bool(config.GEMINI_API_KEY))
print('GROQ_MODEL=', config.GROQ_MODEL)
print('GEMINI_MODEL=', config.GEMINI_MODEL)
