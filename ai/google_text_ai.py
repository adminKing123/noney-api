import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage, AIMessage
from ai.base import BaseAI
from .google_text_context import get_google_text_context
from .contextprovider import ContextProvider
from config import CONFIG

class GeminiTextAI(BaseAI):
    MAPPINGS = CONFIG.AI_MAPPINGS

    def __init__(
        self,
        model_name,
        system_prompt=None,
        temperature=0.7,
        top_p=1.0,
        top_k=40,
    ):
        self.model_name = model_name
        self.details = self.MAPPINGS.get(model_name, {})
        self.model = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=self.details.get("temperature", temperature),
            top_p=self.details.get("top_p", top_p),
            top_k=self.details.get("top_k", top_k),
        )
        self.system_prompt = system_prompt

    def stream(self, payload):
        start_time = time.time()
        user = payload.get("user", {})
        user_id = user.get("user_id", None)
        chat_uid = payload.get("chat_uid", None)
        prompt = payload.get("prompt", "")

        yield self._send_step("info", "Summarizing context")
        ctx = ContextProvider.get(self.details.get("model_id"), user_id, chat_uid, self.system_prompt)
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
