import time
from google import genai
from ai.base import BaseAI
from config import CONFIG
from utils.files import save_file
import io
from werkzeug.datastructures import FileStorage
import uuid
from db import db

class GeminiImageAI(BaseAI):
    MAPPINGS = CONFIG.AI_MAPPINGS

    def __init__(
        self,
        model_name,
        system_prompt=None,
        temperature=0.7,
        top_p=1.0,
        top_k=40,
    ):
        self.details = self.MAPPINGS.get(model_name, {})
        self.model_name = model_name

        self.temperature = self.details.get("temperature", temperature)
        self.top_p = self.details.get("top_p", top_p)
        self.top_k = self.details.get("top_k", top_k)
        
        self.client = genai.Client(api_key=CONFIG.GOOGLE_API_KEY)
        self.system_prompt = self.details.get("system_prompt", system_prompt)

    def stream(self, payload):
        start_time = time.time()
        user = payload.get("user", {})
        user_id = user.get("user_id", None)
        chat_id = payload.get("chat_id", None)
        prompt = payload.get("prompt", "")

        file_id = str(uuid.uuid4())
        index = 0
        
        yield self._send_step("image_generation", "Generating image")
        
        response = self.client.models.generate_images(
            model=self.details.get("model_id"),
            prompt=prompt,
            config=genai.types.GenerateImagesConfig(
                number_of_images=1,
                output_mime_type="image/png",
            )
        )

        if response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            byte_stream = io.BytesIO(img_bytes)
            byte_stream.seek(0)
            fake_file = FileStorage(
                stream=byte_stream,
                filename=f"{file_id}.png",
                content_type="image/png"
            )
            yield self._send_step("image_generation", "Preparing generated image")
            save_file_result = save_file(
                file=fake_file,
                user_id=user_id,
                file_id=file_id,
                file_type="image/png"
            )
            db.file.add_file(user_id, save_file_result, chat_id=chat_id)
            yield self._send_generated_images([save_file_result], index=index)
        end_time = time.time()
        duration = end_time - start_time
        yield self._send_duration(duration)
        yield self._end()

    def invoke(self, payload):
        pass
