from ai.base import BaseAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage

class GeminiTextAI(BaseAI):
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model = ChatGoogleGenerativeAI(model=model_name)

    def stream(self, payload):
        user = payload.get("user", {})
        user_id = user.get("user_id", None)
        chat_uid = payload.get("chat_uid", None)
        prompt = payload.get("prompt", "")

        if (chat_uid and user_id):
            pass

        yield self._start()

        for chunk in self.model.stream([HumanMessage(content=prompt)]):
            yield self._text(chunk.content)

        yield self._end()

    def invoke(self, payload):
        prompt = payload.get("prompt", "")
        return self.model.invoke([HumanMessage(content=prompt)])