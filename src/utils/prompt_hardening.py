def harden_prompt(context):
    # very small placeholder for prompt injection resistance
    # strip suspicious tokens
    if isinstance(context, dict):
        ctx = str(context)
    else:
        ctx = context
    return ctx.replace("ignore instructions", "").replace("are you ai", "")
