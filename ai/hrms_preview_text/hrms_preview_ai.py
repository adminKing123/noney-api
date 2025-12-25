import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage, AIMessage, AIMessageChunk, ToolMessage
from ai.base import BaseAI
from langchain.agents import create_agent
from .tools import get_a_user
# from ..contextprovider import ContextProvider
from config import CONFIG

class HrmsPreviewAI(BaseAI):
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
            model=self.details.get("model_id"),
            temperature=self.details.get("temperature", temperature),
            top_p=self.details.get("top_p", top_p),
            top_k=self.details.get("top_k", top_k),
        )
        self.system_prompt = self.details.get("system_prompt", system_prompt)
        self.agent = create_agent(
            model=self.model,
            tools=[get_a_user],
        )

    def stream(self, payload):
        start_time = time.time()
        user = payload.get("user", {})
        user_id = user.get("user_id", None)
        chat_uid = payload.get("chat_uid", None)
        prompt = payload.get("prompt", "")

        # yield self._send_step("info", "Summarizing context")
        # ctx = ContextProvider.get(self.model_name, user_id, chat_uid, self.system_prompt)
        # context = ctx.build_context(prompt)

        ai_response = ""
        yield self._start()

        started = False

        for msg, meta in self.agent.stream(
            {"messages": [HumanMessage(content=prompt)]},
            stream_mode="messages",
        ):
            if isinstance(msg, AIMessageChunk):
                fc = msg.additional_kwargs.get("function_call")
                if fc:
                    tool_name = fc["name"]
                    tool_args = fc["arguments"]
                    yield self._tool_call(tool_name, tool_args)


            if isinstance(msg, ToolMessage):
                yield self._tool_result(msg.name, msg.content)


            if isinstance(msg, AIMessageChunk) and msg.content:
                if (not started):
                    yield self._started()
                    started = True
                if isinstance(msg.content, list):
                    for part in msg.content:
                        if part.get("type") == "text":
                            # print(part["text"], end="", flush=True)
                            ai_response += part["text"]
                            yield self._text(part["text"])
                else:
                    # print(msg.content, end="", flush=True)
                    ai_response += msg.content
                    yield self._text(msg.content)

        # ctx.append(AIMessage(content=ai_response))
        end_time = time.time()
        duration = end_time - start_time
        yield self._send_duration(duration)
        yield self._end()

    def invoke(self, payload):
        prompt = payload.get("prompt", "")
        return prompt
