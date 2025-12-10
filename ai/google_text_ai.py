from ai.base import BaseAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage

class GeminiTextAI(BaseAI):
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model = ChatGoogleGenerativeAI(model=model_name)

    def stream(self, messages):
        yield self._start()

        for chunk in self.model.stream(messages):
            yield self._text(chunk.content)

        yield self._end()

    def invoke(self, messages):
        return self.model.invoke(messages)
