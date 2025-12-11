import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage, AIMessage
from ai.base import BaseAI
from .google_text_context import get_google_text_context

class GeminiTextAI(BaseAI):
    def __init__(
        self,
        model_name="gemini-2.5-flash",
        temperature=0.7,
        top_p=1.0,
        top_k=40,
    ):
        self.model = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )

    def stream(self, payload):
        start_time = time.time()
        user = payload.get("user", {})
        user_id = user.get("user_id", None)
        chat_uid = payload.get("chat_uid", None)
        prompt = payload.get("prompt", "")

        yield self._send_step("info", "Summarizing context")
        ctx = get_google_text_context(user_id, chat_uid)
        context = ctx.build_context(prompt)

        ai_response = ""
        yield self._start()

        started = False
        for chunk in self.model.stream(context):
            if (not started):
                yield self._started()
                started = True
            ai_response += chunk.content
            yield self._text(chunk.content)

        ctx.append(AIMessage(content=ai_response))
        end_time = time.time()
        duration = end_time - start_time
        yield self._send_duration(duration)
        yield self._end()

    def invoke(self, payload):
        prompt = payload.get("prompt", "")
        return self.model.invoke([HumanMessage(content=prompt)])
